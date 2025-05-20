from elasticsearch import Elasticsearch
from aiogram import Bot, types
import pandas as pd
from sklearn.ensemble import IsolationForest
import numpy as np
import re
import asyncio
from dotenv import load_dotenv
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()  # Загружает переменные из .env
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST', 'elasticsearch')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID в .env")

# Инициализация ML-модели
model = IsolationForest(
    n_estimators=100,
    contamination=0.01,  # 1% аномалий
    random_state=42
)

# Подключение к Elasticsearch
es = Elasticsearch([f'http://{ELASTICSEARCH_HOST}:9200'])

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Шаблоны опасных запросов
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
    """Извлечение признаков для ML-модели"""
    return np.array([
        len(query),  # Длина запроса
        len(re.findall(r'\bSELECT\b', query, re.IGNORECASE)),
        len(re.findall(r'\bWHERE\b', query, re.IGNORECASE)),
        len(re.findall(r'\bJOIN\b', query, re.IGNORECASE)),
        len(re.findall(r';--', query)),  # SQL-инъекции
        len(re.findall(r'\bUNION\b', query, re.IGNORECASE))
    ]).reshape(1, -1)


def check_dangerous_queries(query):
    """Комбинированная проверка: правила + ML"""
    # Проверка по регулярным выражениям
    query_lower = query.lower()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, query_lower):
            return True, pattern

    # Проверка через ML-модель
    features = extract_features(query)
    prediction = model.predict(features)
    if prediction[0] == -1:
        return True, "ML-аномалия"

    return False, None


async def send_alert(message):
    """Отправка уведомления в Telegram"""
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


async def train_model():
    """Обучение модели на исторических данных"""
    # Получение данных из Elasticsearch
    query = {"query": {"match_all": {}}, "size": 1000}
    res = es.search(index="postgresql-logs-*", body=query)

    # Преобразование в DataFrame
    df = pd.DataFrame([
        {
            "timestamp": hit["_source"]["@timestamp"],
            "query": hit["_source"].get("query", ""),
            "user": hit["_source"].get("user", "")
        }
        for hit in res["hits"]["hits"]
    ])

    # Сбор признаков
    X = np.array([extract_features(q) for q in df["query"]])

    # Обучение модели
    if len(X) > 0:
        model.fit(X)
        print(f"Модель обучена на {len(df)} записях")

async def check_bot():
    try:
        await bot.get_me()
    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {e}")
        exit(1)

async def check_elastic():
    try:
        if not await es.ping():
            logger.critical("Не удалось подключиться к Elasticsearch!")
            exit(1)
        logger.info("Подключение к Elasticsearch успешно")
    except Exception as e:
        logger.critical(f"Ошибка подключения к Elasticsearch: {e}")
        exit(1)

async def monitor_logs():
    """Мониторинг логов в реальном времени"""
    await check_bot()
    await check_elastic()
    await train_model()  # Первоначальное обучение
    last_checked_time = None
    # Проверка подключения к Elasticsearch
    if not es.ping():
        logger.error("Не удалось подключиться к Elasticsearch!")
        exit(1)
    while True:
        try:
            # Поиск новых логов
            query = {"query": {"range": {"@timestamp": {"gt": last_checked_time}}}}
            res = es.search(index="postgresql-logs-*", body=query)

            if res['hits']['hits']:
                last_checked_time = res['hits']['hits'][-1]['_source']['@timestamp']

                for hit in res['hits']['hits']:
                    source = hit['_source']
                    query_text = source.get('query', '')

                    # Комбинированная проверка
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
            await send_alert(error_msg)

        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(monitor_logs())