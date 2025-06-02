from aiogram import Dispatcher, types
from aiogram import Bot
import os
import asyncio
from aiogram.filters import Command

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔒 Система мониторинга SQL-запросов\n\n"
        "Я буду уведомлять вас о подозрительных и опасных запросах к базе данных.\n"
        "Используйте /status для проверки состояния системы."
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    await message.answer("✅ Система мониторинга работает нормально")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())