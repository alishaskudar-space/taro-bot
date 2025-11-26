import asyncio
import random
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile

API_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Список карт (пока без картинок — будут текстовые, потом добавишь)
CARDS = [
    "Дурак", "Маг", "Верховная Жрица", "Императрица", "Император", "Иерофант", "Влюблённые",
    "Колесница", "Сила", "Отшельник", "Колесо Фортуны", "Правосудие", "Повешенный", "Смерть",
    "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир"
] + [f"{rank} {suit}" for suit in ["Жезлов", "Кубков", "Мечей", "Пентаклей"] for rank in ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"]]

@dp.message(Command("start"))
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [types.KeyboardButton(text="Одна карта")],
        [types.KeyboardButton(text="Три карты")],
        [types.KeyboardButton(text="Кельтский крест")]
    ])
    await message.answer(
        "Привет! Я — Таро-бот Светлана ✨\n"
        "Выбери расклад и получи ответ от карт 🔮",
        reply_markup=keyboard
    )

@dp.message(F.text == "Одна карта")
async def one_card(message: types.Message):
    card = random.choice(CARDS)
    orient = random.choice(["(прямое)", "(перевёрнутое)"])
    await message.answer(f"Ваша карта дня:\n\n{card} {orient}\n\nТолкование скоро будет тут ✨")

@dp.message(F.text == "Три карты")
async def three_cards(message: types.Message):
    cards = [random.choice(CARDS) for _ in range(3)]
    await message.answer("Прошлое — Настоящее — Будущее:\n\n" +
                         f"Прошлое: {cards[0]}\nНастоящее: {cards[1]}\nБудущее: {cards[2]}")

@dp.message(F.text == "Кельтский крест")
async def celtic(message: types.Message):
    cards = [random.choice(CARDS) for _ in range(10)]
    await message.answer("Кельтский крест (10 карт):\n" + "\n".join(f"{i+1}. {c}" for i, c in enumerate(cards)))

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
