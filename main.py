import asyncio
import json
import os
import random
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    PreCheckoutQuery,
)

# =========================
# ENV
# =========================
API_TOKEN = os.getenv("BOT_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")  # token from @BotFather after connecting Portmone

if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not PROVIDER_TOKEN:
    raise RuntimeError("PROVIDER_TOKEN is not set (get it from @BotFather -> Payments -> Portmone)")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

CARDS_FOLDER = "cards"

# =========================
# PAYWALL / PACKS
# =========================
FREE_READINGS = 3
STATE_PATH = Path(os.getenv("STATE_PATH", "users_state.json"))
_state_lock = asyncio.Lock()
_state: dict[str, dict] = {}  # user_id(str) -> {"free_used": int, "credits": int, "natal": bool}

# Важно: Portmone может требовать UAH. Ты просила $ — ставлю USD.
# Если invoice не создаётся, поменяй CURRENCY="UAH" и цены в копейках гривны.
CURRENCY = "USD"

PACKS = {
    "pack_5": {
        "title": "🪄 Купить 5 гаданий",
        "description": "✨ Пять гаданий — и я открою тебе больше знаков, чем видят обычные глаза.\n"
                       "Подходит, чтобы проверять чувства, планы и исходы — без ожидания.",
        "credits": 5,
        "amount": 299,  # cents
        "label": "5 гаданий",
    },
    "pack_10_natal": {
        "title": "🔮 Купить 10 гаданий + Натальная карта",
        "description": "🌙 Десять гаданий + доступ к «Натальной карте».\n"
                       "Я посмотрю не только в арканы — но и в твой небесный код.",
        "credits": 10,
        "amount": 499,  # cents
        "label": "10 гаданий + Натальная карта",
        "natal": True,
    },
}


# =========================
# TAROT CONTENT
# =========================
MEANINGS = {
    "00": {
        "up": "Дурак открывает дверь в новую главу твоей судьбы, полную возможностей. Доверься потоку — он ведёт тебя туда, где случается чудо.",
        "rev": "Ты боишься шагнуть в неизвестность или действуешь слишком импульсивно. Замедлись, проверь опору — и сделай ход осознанно.",
    },
    "01": {
        "up": "Маг напоминает: у тебя уже есть всё, чтобы создать желаемое. Сфокусируй волю — и реальность начнёт отвечать.",
        "rev": "Сомнения или хаос распыляют силу. Собери энергию в одну точку — и перестань отдавать власть страхам и чужим словам.",
    },
    "02": {
        "up": "Верховная Жрица приподнимает завесу: ответ внутри тебя. Доверься интуиции и тишине — там живёт правда.",
        "rev": "Ты игнорируешь знаки или слишком спешишь. Пауза сейчас — это не остановка, а ключ к верному решению.",
    },
}

NAMES = {"00": "0. Дурак", "01": "I. Маг", "02": "II. Верховная Жрица"}


# =========================
# STATE HELPERS
# =========================
def _default_user_state() -> dict:
    return {"free_used": 0, "credits": 0, "natal": False}


def _load_state_sync() -> dict[str, dict]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state_sync(state: dict[str, dict]) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


async def load_state() -> None:
    global _state
    async with _state_lock:
        _state = await asyncio.to_thread(_load_state_sync)


async def save_state() -> None:
    async with _state_lock:
        await asyncio.to_thread(_save_state_sync, _state)


async def get_user_state(user_id: int) -> dict:
    uid = str(user_id)
    async with _state_lock:
        if uid not in _state:
            _state[uid] = _default_user_state()
        return _state[uid]


async def add_credits(user_id: int, credits: int, natal: bool = False) -> dict:
    uid = str(user_id)
    async with _state_lock:
        if uid not in _state:
            _state[uid] = _default_user_state()
        _state[uid]["credits"] = int(_state[uid].get("credits", 0)) + int(credits)
        if natal:
            _state[uid]["natal"] = True
    await save_state()
    return await get_user_state(user_id)


async def consume_reading_or_block(message: types.Message) -> bool:
    """
    True -> можно гадать (списали 1 бесплатное или 1 кредит)
    False -> заблокировали и показали продажный текст + кнопки оплаты
    """
    user_id = message.from_user.id
    uid = str(user_id)

    async with _state_lock:
        if uid not in _state:
            _state[uid] = _default_user_state()

        st = _state[uid]
        credits = int(st.get("credits", 0))
        free_used = int(st.get("free_used", 0))

        if credits > 0:
            st["credits"] = credits - 1
            allowed = True
        elif free_used < FREE_READINGS:
            st["free_used"] = free_used + 1
            allowed = True
        else:
            allowed = False

    if allowed:
        await save_state()
        return True

    await message.answer(
        "🧙‍♂️✨ *Стой, искатель тайн!* ✨\n\n"
        "Три бесплатных гадания уже исчерпаны — арканы требуют энергию для новых откровений.\n\n"
        "🔮 Хочешь продолжить *без ожидания* и получать больше подсказок судьбы?\n"
        "Выбери пакет ниже — и я открою тебе следующий слой магии:",
        parse_mode="Markdown",
        reply_markup=get_paywall_kb(),
    )
    return False


# =========================
# UI
# =========================
def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🔮 Одна карта — совет судьбы")],
        [KeyboardButton(text="🃏 Три карты — путь души")],
        [KeyboardButton(text="✨ Кельтский крест — полное гадание")],
        [KeyboardButton(text="❓ Да / Нет — быстрый ответ")],
        [KeyboardButton(text="🪐 Натальная карта")],
        [KeyboardButton(text="💳 Купить гадания")],
    ])


def get_paywall_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪄 Купить 5 гаданий — $2.99", callback_data="buy_pack_5")],
        [InlineKeyboardButton(text="🔮 Купить 10 гаданий + 🪐 — $4.99", callback_data="buy_pack_10")],
        [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_menu")],
    ])


# =========================
# PAYMENTS
# =========================
async def send_pack_invoice(chat_id: int, pack_key: str) -> None:
    if pack_key not in PACKS:
        raise ValueError("Unknown pack")

    pack = PACKS[pack_key]
    prices = [LabeledPrice(label=pack["label"], amount=int(pack["amount"]))]

    await bot.send_invoice(
        chat_id=chat_id,
        title=pack["title"],
        description=pack["description"],
        payload=pack_key,  # вернётся в successful_payment.invoice_payload
        provider_token=PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=prices,
        start_parameter=f"taro-{pack_key}",
    )


@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    sp = message.successful_payment
    payload = sp.invoice_payload
    user_id = message.from_user.id

    if payload == "pack_5":
        st = await add_credits(user_id, credits=PACKS["pack_5"]["credits"], natal=False)
        await message.answer(
            "✅✨ *Магия приняла платёж!* ✨\n\n"
            f"🎴 Начислено: *{PACKS['pack_5']['credits']} гаданий*\n"
            f"📿 Остаток: *{st['credits']}*\n\n"
            "Скажи… что хочешь узнать первым? 🔮",
            parse_mode="Markdown",
            reply_markup=get_main_menu(),
        )
        return

    if payload == "pack_10_natal":
        st = await add_credits(user_id, credits=PACKS["pack_10_natal"]["credits"], natal=True)
        await message.answer(
            "✅🌙 *Сделка с судьбой заключена!* 🌙\n\n"
            f"🎴 Начислено: *{PACKS['pack_10_natal']['credits']} гаданий*\n"
            "🪐 *Натальная карта* теперь доступна.\n"
            f"📿 Остаток: *{st['credits']}*\n\n"
            "Прикажи — и я начну. 🧙‍♂️✨",
            parse_mode="Markdown",
            reply_markup=get_main_menu(),
        )
        return

    await message.answer("✅ Платёж получен. Если что-то не активировалось — напиши /start.")


# =========================
# BOT LOGIC
# =========================
async def ritual_delay(message: types.Message):
    await message.answer(
        "Сосредоточься на вопросе…\n"
        "Дыши глубоко.\n"
        "Колода шепчет в темноте… ✨"
    )
    await asyncio.sleep(2)


def get_random_card():
    code = random.choice(["00", "01", "02"])
    orient = random.choice(["up", "rev"])
    path = os.path.join(CARDS_FOLDER, f"{code}_{orient}.jpg")
    return code, orient, path


@dp.message(Command("start"))
async def start(message: types.Message):
    st = await get_user_state(message.from_user.id)
    free_left = max(0, FREE_READINGS - int(st.get("free_used", 0)))
    credits = int(st.get("credits", 0))

    await message.answer(
        "✨ Я — маг-таролог. Слушаю твой вопрос и читаю знаки судьбы… 🧙‍♂️🔮\n\n"
        f"🎁 Бесплатных гаданий осталось: *{free_left}* из {FREE_READINGS}\n"
        f"📿 Платных гаданий на балансе: *{credits}*\n\n"
        "Выбери ритуал:",
        parse_mode="Markdown",
        reply_markup=get_main_menu(),
    )


@dp.message(F.text == "💳 Купить гадания")
async def show_paywall(message: types.Message):
    await message.answer(
        "🧙‍♂️💫 *Выбери артефакт доступа:*",
        parse_mode="Markdown",
        reply_markup=get_paywall_kb(),
    )


@dp.callback_query(F.data == "buy_pack_5")
async def cb_buy_pack_5(callback: types.CallbackQuery):
    await callback.answer()
    await send_pack_invoice(chat_id=callback.message.chat.id, pack_key="pack_5")


@dp.callback_query(F.data == "buy_pack_10")
async def cb_buy_pack_10(callback: types.CallbackQuery):
    await callback.answer()
    await send_pack_invoice(chat_id=callback.message.chat.id, pack_key="pack_10_natal")


@dp.callback_query(F.data == "back_menu")
async def cb_back_menu(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("🔙 Возвращаю в меню…", reply_markup=get_main_menu())


@dp.message(F.text == "🪐 Натальная карта")
async def natal_chart(message: types.Message):
    st = await get_user_state(message.from_user.id)
    if not st.get("natal", False):
        await message.answer(
            "🪐🔒 *Натальная карта* закрыта печатью звёзд.\n\n"
            "Открою её только тем, кто усилил свой путь пакетом:\n"
            "🔮 *10 гаданий + Натальная карта* — и я расшифрую твой небесный код ✨",
            parse_mode="Markdown",
            reply_markup=get_paywall_kb(),
        )
        return

    await message.answer(
        "🪐✨ *Натальная карта активна!*\n\n"
        "Пока это раздел-заготовка. Следующий шаг: спросить дату, время и место рождения — и построить интерпретацию.",
        parse_mode="Markdown",
    )


@dp.message(F.text == "🔮 Одна карта — совет судьбы")
async def one_card(message: types.Message):
    if not await consume_reading_or_block(message):
        return

    await ritual_delay(message)
    code, orient, path = get_random_card()
    emoji = "✨" if orient == "up" else "🌙"

    caption = (
        f"{emoji} *{NAMES[code]}* {'(прямое)' if orient == 'up' else '(перевёрнутое)'}\n\n"
        f"{MEANINGS[code][orient]}\n\n"
        "Дыши. Ответ уже течёт к тебе."
    )

    if os.path.exists(path):
        await message.answer_photo(FSInputFile(path), caption=caption, parse_mode="Markdown")
    else:
        await message.answer(caption, parse_mode="Markdown")


@dp.message(F.text == "🃏 Три карты — путь души")
async def three_cards(message: types.Message):
    if not await consume_reading_or_block(message):
        return

    await ritual_delay(message)

    cards = [get_random_card() for _ in range(3)]
    media = []
    text = "*Три карты — путь души*\n\n"
    positions = ["🕰 Прошлое", "🌟 Настоящее", "🔮 Будущее"]

    for i, (code, orient, path) in enumerate(cards):
        emoji = "✨" if orient == "up" else "🌙"
        text += (
            f"{positions[i]}\n"
            f"{emoji} *{NAMES[code]}* {'(прямое)' if orient == 'up' else '(перевёрнутое)'}\n"
            f"{MEANINGS[code][orient]}\n\n"
        )
        if os.path.exists(path):
            media.append(types.InputMediaPhoto(media=FSInputFile(path)))

    if media:
        await message.answer_media_group(media)

    await message.answer(text + "Три нити сплелись. Судьба уже двигается…", parse_mode="Markdown")


@dp.message(F.text == "✨ Кельтский крест — полное гадание")
async def celtic_cross(message: types.Message):
    if not await consume_reading_or_block(message):
        return

    await ritual_delay(message)
    await message.answer(
        "*Кельтский крест*\n\n"
        "Скоро здесь будет полное гадание на 10 карт. Пока — почувствуй энергию расклада ✨",
        parse_mode="Markdown",
    )


@dp.message(F.text == "❓ Да / Нет — быстрый ответ")
async def yes_no(message: types.Message):
    if not await consume_reading_or_block(message):
        return

    await ritual_delay(message)
    answers = [
        "✅ Да. Арканы говорят ясно.",
        "❌ Нет. Дверь сейчас закрыта — не ломись в неё.",
        "❓ Возможно. Если изменишь курс — шанс появится.",
    ]
    await message.answer(random.choice(answers))


async def main():
    await load_state()
    print("🧙‍♂️ Бот готов к ритуалу…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
