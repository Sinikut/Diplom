from elasticsearch import AsyncElasticsearch
from aiogram import Bot
import pandas as pd
from sklearn.ensemble import IsolationForest
import numpy as np
import re
import asyncio
from dotenv import load_dotenv
import os
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST', 'elasticsearch')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    logger.critical("Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID в .env")
    exit(1)

# Инициализация ML-модели
model = IsolationForest(
    n_estimators=100,
    contamination=0.01,
    random_state=42
)

# Асинхронный клиент Elasticsearch
es = AsyncElasticsearch([f'http://{ELASTICSEARCH_HOST}:9200'])
bot = Bot(token=TELEGRAM_BOT_TOKEN)

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


def extract_features(query):
    """Синхронная обработка запроса"""
    return np.array([
        len(query),
        len(re.findall(r'\bSELECT\b', query, re.IGNORECASE)),
        len(re.findall(r'\bWHERE\b', query, re.IGNORECASE)),
        len(re.findall(r'\bJOIN\b', query, re.IGNORECASE)),
        len(re.findall(r';--', query)),
        len(re.findall(r'\bUNION\b', query, re.IGNORECASE))
    ]).reshape(1, -1)


def check_dangerous_queries(query):
    """Синхронная проверка запроса"""
    query_lower = query.lower()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, query_lower):
            return True, pattern

    features = extract_features(query)
    prediction = model.predict(features)
    if prediction[0] == -1:
        return True, "ML-аномалия"

    return False, None


async def send_alert(message):
    """Отправка уведомления"""
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")


async def train_model():
    """Обучение модели"""
    try:
        query = {"query": {"match_all": {}}, "size": 1000}
        res = await es.search(index="postgresql-logs-*", body=query)

        df = pd.DataFrame([
            {
                "timestamp": hit["_source"]["@timestamp"],
                "query": hit["_source"].get("query", ""),
                "user": hit["_source"].get("user", "")
            }
            for hit in res["hits"]["hits"]
        ])

        if not df.empty:
            X = np.array([extract_features(q) for q in df["query"]])
            model.fit(X)
            logger.info(f"Модель обучена на {len(df)} записях")

    except Exception as e:
        logger.error(f"Ошибка обучения модели: {e}")
        await send_alert(f"Ошибка обучения модели: {e}")


async def check_connections():
    """Проверка подключений"""
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

        last_checked_time = None
        query = {"query": {"range": {"@timestamp": {"gt": last_checked_time}}}}
        res = await es.search(index="postgresql-logs-*", body=query)

        if res['hits']['hits']:
            last_checked_time = res['hits']['hits'][-1]['_source']['@timestamp']

            for hit in res['hits']['hits']:
                source = hit['_source']
                query_text = source.get('query', '')

                is_dangerous, reason = check_dangerous_queries(query_text)
                if is_dangerous:
                    alert_msg = (
                        f"Обнаружена аномалия!\n"
                        f"Время: {source['@timestamp']}\n"
                        f"Пользователь: {source.get('user', 'N/A')}\n"
                        f"Запрос: {query_text[:300]}...\n"
                        f"Причина: {reason}"
                    )
                    await send_alert(alert_msg)

    except Exception as e:
        error_msg = f"Ошибка мониторинга: {str(e)}"
        logger.error(error_msg)
        await send_alert(error_msg)


async def main():
    """Основная функция инициализации"""
    await check_connections()
    await train_model()

    # Настройка планировщика
    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))
    scheduler.add_job(
        monitor_logs,
        IntervalTrigger(seconds=30),
        max_instances=1
    )
    scheduler.start()

    # Бесконечный цикл
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