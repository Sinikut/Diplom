import os
from elasticsearch import Elasticsearch
from aiogram import Bot, types
import pandas as pd
from sklearn.ensemble import IsolationForest
import re
import asyncio

# Конфигурация
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST', 'elasticsearch')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

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


def check_dangerous_queries(query):
    """Проверка запроса на наличие опасных паттернов"""
    query_lower = query.lower()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, query_lower):
            return True, pattern
    return False, None


async def send_alert(message):
    """Отправка уведомления в Telegram"""
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


async def monitor_logs():
    """Мониторинг логов и обнаружение аномалий"""
    last_checked_time = None

    while True:
        try:
            # Поиск новых логов
            query = {
                "query": {
                    "range": {
                        "@timestamp": {
                            "gt": last_checked_time.isoformat() if last_checked_time else "now-1m"
                        }
                    }
                },
                "size": 100,
                "sort": [{"@timestamp": "asc"}]
            }

            res = es.search(index="postgresql-logs-*", body=query)

            if res['hits']['hits']:
                last_checked_time = pd.to_datetime(res['hits']['hits'][-1]['_source']['@timestamp'])

                for hit in res['hits']['hits']:
                    source = hit['_source']
                    query_text = source.get('query', '')

                    # Проверка на опасные запросы
                    is_dangerous, pattern = check_dangerous_queries(query_text)
                    if is_dangerous:
                        alert_msg = (
                            f"⚠️ Опасный SQL-запрос обнаружен!\n"
                            f"🕒 Время: {source['@timestamp']}\n"
                            f"👤 Пользователь: {source.get('user', 'N/A')}\n"
                            f"📝 Запрос: {query_text[:500]}...\n"
                            f"🔍 Паттерн: {pattern}\n"
                            f"❗️ Требуется немедленное вмешательство!"
                        )
                        await send_alert(alert_msg)

                        # Напоминание!!! добавить автоматическую блокировку пользователя

        except Exception as e:
            error_msg = f"Ошибка при мониторинге логов: {str(e)}"
            await send_alert(error_msg)
            print(error_msg)

        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(monitor_logs())