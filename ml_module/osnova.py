import asyncio
import logging
from aiogram import Bot
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
# Загрузка .env
load_dotenv()

# Настройки
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Telegram-бот
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Счётчик сообщений
anomaly_count = 0
max_alerts = 2

async def send_fake_anomaly():
    global anomaly_count

    anomaly_query = "DROP DATABASE testdb;"
    user = "user"
    database = "postgres"

    while anomaly_count < max_alerts:
        timestamp = datetime.now(timezone.utc).isoformat()

        message = (
            f"🚨 Обнаружена аномалия!\n\n"
            f"⏱ Время: {timestamp}\n"
            f"👤 Пользователь: {user}\n"
            f"🗄 База данных: {database}\n"
            f"📄 Запрос: {anomaly_query}"
        )

        logger.warning(
            f"Аномалия №{anomaly_count + 1}: {anomaly_query}, пользователь: {user}, БД: {database}, время: {timestamp}"
        )

        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")

        anomaly_count += 1
        await asyncio.sleep(20)  # Пауза, чтобы не отправлять мгновенно

    logger.info("Максимальное число предупреждений достигнуто. Отправка остановлена.")


if __name__ == "__main__":
    asyncio.run(send_fake_anomaly())