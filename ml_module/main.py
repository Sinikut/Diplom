from elasticsearch import AsyncElasticsearch
from aiogram import Bot
import pandas as pd
from sklearn.ensemble import IsolationForest
import numpy as np
import re
import asyncio
from dotenv import load_dotenv
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz
import os
import sys

# Перенаправление stdout/stderr в лог-файлы
sys.stdout = open('/var/log/app_out.log', 'a')
sys.stderr = open('/var/log/app_err.log', 'a')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных из .env
load_dotenv()
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST', 'elasticsearch')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Проверка обязательных переменных
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    logger.critical("Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID в .env")
    exit(1)

# Инициализация модели
model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)

# Инициализация бота и Elasticsearch
es = AsyncElasticsearch([f'http://{ELASTICSEARCH_HOST}:9200'])
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Подозрительные шаблоны
DANGEROUS_PATTERNS = [
    r'drop\s+database',
    r'truncate\s+table',
    r'delete\s+from\s+\w+\s*(?!where)',
    r'alter\s+table\s+\w+\s+drop',
    r';\s*--',
    r'1\s*=\s*1',
    r'union\s+select',
    r'insert\s+into\s+\w+\s+values',
    r'update\s+\w+\s+set\s+\w+\s*=\s*\w+\s*(?!where)'
]

def extract_features(query: str):
    return np.array([
        len(query),
        len(re.findall(r'\bSELECT\b', query, re.IGNORECASE)),
        len(re.findall(r'\bWHERE\b', query, re.IGNORECASE)),
        len(re.findall(r'\bJOIN\b', query, re.IGNORECASE)),
        len(re.findall(r';--', query)),
        len(re.findall(r'\bUNION\b', query, re.IGNORECASE))
    ]).reshape(1, -1)

async def send_alert(message: str):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

async def train_model():
    """Обучение модели с проверкой данных"""
    await asyncio.sleep(15)  # дать системе стартовать
    try:
        logger.info("🔍 Запуск обучения модели...")

        query = {
            "query": {"exists": {"field": "postgresql.message"}},
            "size": 100,
            "sort": [{"@timestamp": {"order": "desc"}}]
        }
        res = await es.search(index="postgresql-logs-*", body=query)

        messages = [
            hit["_source"]["postgresql"]["message"]
            for hit in res["hits"]["hits"]
            if "postgresql" in hit["_source"] and "message" in hit["_source"]["postgresql"]
        ]

        if not messages:
            logger.warning("Нет данных для обучения")
            return False

        X = np.vstack([extract_features(q) for q in messages])
        model.fit(X)
        logger.info(f"✅ Модель обучена на {len(messages)} записях")
        return True

    except Exception as e:
        logger.error(f"Ошибка обучения модели: {e}")
        await send_alert(f"Ошибка обучения модели: {e}")
        return False

def check_dangerous_queries(query):
    """Проверка запроса с обработкой необученной модели"""
    if not hasattr(model, 'estimators_'):
        return False, "Модель не обучена"

    query_lower = query.lower()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, query_lower):
            return True, pattern

    try:
        features = extract_features(query)
        prediction = model.predict(features)
        if prediction[0] == -1:
            return True, "ML-аномалия"
    except Exception as e:
        logger.error(f"Ошибка предсказания: {e}")
        return False, str(e)

    return False, None

async def check_connections():
    """Проверка подключений"""
    await asyncio.sleep(15)  # дать системе стартовать
    try:
        # Проверка бота
        await bot.get_me()
        # Проверка Elasticsearch
        if not await es.ping():
            raise ConnectionError("Elasticsearch не доступен")
        logger.info("Все подключения активны")
        return True
    except Exception as e:
        logger.critical(f"Ошибка подключений: {e}")
        await send_alert(f"Критическая ошибка: {e}")
        exit(1)

async def monitor_logs():
    """Основная задача мониторинга"""
    try:
        if not await check_connections():
            return

        # Загрузка последнего времени из файла
        try:
            with open('last_checked_time.txt', 'r') as f:
                last_checked_time = f.read().strip() or None
        except FileNotFoundError:
            last_checked_time = None

        query = {
            "query": {
                "range": {
                    "@timestamp": {
                        "gt": last_checked_time,
                        "format": "strict_date_optional_time"
                    }
                }
            },
            "sort": [{"@timestamp": {"order": "asc"}}]
        }

        res = await es.search(index="postgresql-logs-*", body=query)

        if res['hits']['hits']:
            new_last_time = res['hits']['hits'][-1]['_source']['@timestamp']
            with open('last_checked_time.txt', 'w') as f:
                f.write(new_last_time)

            for hit in res['hits']['hits']:
                source = hit['_source']
                query_text = source.get("postgresql", {}).get("message", "")
                user = source.get('user', 'N/A')
                database = "postgres"
                timestamp = source['@timestamp']

                if query_text:
                    is_dangerous, reason = check_dangerous_queries(query_text)
                    if is_dangerous:
                        message = (
                            f"🚨 Обнаружена аномалия!\n\n"
                            f"⏱ Время: {timestamp}\n"
                            f"👤 Пользователь: {user}\n"
                            f"🗄 База данных: {database}\n"
                            f"🔍 Причина: {reason}\n"
                            f"Запрос: {query_text.strip()}"
                        )
                        await send_alert(message)

    except Exception as e:
        logger.error(f"Ошибка мониторинга: {e}")
        await send_alert(f"Ошибка мониторинга: {e}")

async def main():
    """Основная функция инициализации"""
    await check_connections()

    # Обучаем модель с повторными попытками
    trained = False
    for attempt in range(3):
        trained = await train_model()
        if trained:
            break
        logger.warning(f"Попытка {attempt + 1} неудачна. Повтор через 5 секунд...")
        await asyncio.sleep(5)

    if not trained:
        logger.critical("Не удалось обучить модель после 3 попыток")
        await send_alert("Критическая ошибка: не удалось обучить модель")
        return

    # Настройка планировщика только после успешного обучения
    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))
    scheduler.add_job(monitor_logs, IntervalTrigger(seconds=30), max_instances=1)
    scheduler.start()

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Приложение остановлено")
    finally:
        asyncio.run(es.close())
        asyncio.run(bot.session.close())