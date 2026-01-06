import asyncio
import json
import os
import random
import time
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
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")  # provider token from @BotFather (Portmone TEST/Live)

if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not PROVIDER_TOKEN:
    raise RuntimeError("PROVIDER_TOKEN is not set (get it from @BotFather -> Payments -> Portmone)")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

CARDS_FOLDER = "cards"

# =========================
# DISCLAIMER (UA)
# =========================
DISCLAIMER_TEXT = (
    "📜 *Дисклеймер*\n\n"
    "🪄 Відповіді цього бота мають *розважальний та ігровий характер* і є "
    "*суб’єктивною інтерпретацією випадково обраних символів/карт*.\n\n"
    "Це *не є* достовірним прогнозом майбутнього, гарантією результатів або "
    "професійною консультацією.\n\n"
    "❗️Бот *не надає* юридичних, медичних чи фінансових порад.\n"
    "Рішення ви приймаєте самостійно."
)

# =========================
# PAYWALL / PACKS
# =========================
FREE_READINGS = 3
STATE_PATH = Path(os.getenv("STATE_PATH", "users_state.json"))
_state_lock = asyncio.Lock()
_state: dict[str, dict] = {}  # user_id(str) -> {"free_used": int, "credits": int, "natal": bool}

# Portmone зазвичай працює з UAH у Telegram Payments
CURRENCY = "UAH"

PACKS = {
    "pack_5": {
        "title": "🪄 Пакет «5 ворожінь»",
        "description": (
            "✨ П’ять ворожінь — і я відкрию тобі більше знаків, ніж бачать звичайні очі.\n"
            "Ідеально, щоб швидко перевіряти почуття, плани та можливі розв’язки."
        ),
        "credits": 5,
        "amount": 299,  # 2.99 UAH (копійки)
        "label": "5 ворожінь",
        "natal": False,
    },
    "pack_10_natal": {
        "title": "🔮 Пакет «10 ворожінь + 🪐 Натальна карта»",
        "description": (
            "🌙 Десять ворожінь + доступ до «Натальної карти».\n"
            "Я подивлюся не лише на карти — а й на твій небесний код."
        ),
        "credits": 10,
        "amount": 499,  # 4.99 UAH (копійки)
        "label": "10 ворожінь + Натальна карта",
        "natal": True,
    },
}

# =========================
# TAROT CONTENT (UA)
# =========================
MEANINGS = {
    "00": {
        "up": "Дурень відчиняє двері в новий розділ твоєї історії. Довірся потоку — він веде туди, де народжується диво.",
        "rev": "Ти боїшся кроку в невідоме або дієш надто імпульсивно. Сповільнись, перевір опору — і зроби хід усвідомлено.",
    },
    "01": {
        "up": "Маг нагадує: у тебе вже є все, щоб створити бажане. Сфокусуй волю — і реальність почне відповідати.",
        "rev": "Сумніви або хаос розпорошують силу. Збери енергію в одну точку — і не віддавай владу страхам.",
    },
    "02": {
        "up": "Верховна Жриця піднімає завісу: відповідь всередині тебе. Довірся інтуїції та тиші — там живе правда.",
        "rev": "Ти ігноруєш знаки або поспішаєш. Пауза зараз — не зупинка, а ключ до правильного рішення.",
    },
}

NAMES = {"00": "0. Дурень", "01": "I. Маг", "02": "II. Верховна Жриця"}


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


def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🔮 Одна карта — порада долі")],
        [KeyboardButton(text="🃏 Три карти — шлях душі")],
        [KeyboardButton(text="✨ Кельтський хрест — повне ворожіння")],
        [KeyboardButton(text="❓ Так / Ні — швидка відповідь")],
        [KeyboardButton(text="🪐 Натальна карта")],
        [KeyboardButton(text="💳 Купити ворожіння")],
        [KeyboardButton(text="📜 Дисклеймер")],
    ])


def get_paywall_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪄 Купити 5 ворожінь — 2.99 ₴", callback_data="buy_pack_5")],
        [InlineKeyboardButton(text="🔮 Купити 10 ворожінь + 🪐 — 4.99 ₴", callback_data="buy_pack_10")],
        [InlineKeyboardButton(text="📜 Дисклеймер", callback_data="show_disclaimer")],
        [InlineKeyboardButton(text="🔙 Назад у меню", callback_data="back_menu")],
    ])


def get_disclaimer_confirm_kb(pack_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Погоджуюсь і перейти до оплати", callback_data=f"confirm_{pack_key}")],
        [InlineKeyboardButton(text="📜 Показати дисклеймер ще раз", callback_data="show_disclaimer")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="back_menu")],
    ])


# =========================
# PAYWALL LOGIC
# =========================
async def consume_reading_or_block(message: types.Message) -> bool:
    """
    True -> можна ворожити (списали 1 безкоштовне або 1 кредит)
    False -> показали paywall
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
        "🧙‍♂️✨ *Стій, шукачу таємниць!* ✨\n\n"
        f"Ти вже використав(ла) *{FREE_READINGS}* безкоштовні ворожіння.\n"
        "Щоб я міг відкрити наступний шар підказок долі — потрібна енергія обміну.\n\n"
        "🔮 Обери пакунок нижче — і я продовжу читати знаки для тебе:",
        parse_mode="Markdown",
        reply_markup=get_paywall_kb(),
    )
    return False


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
        payload=pack_key,  # повернеться в successful_payment.invoice_payload
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

    if payload in PACKS:
        pack = PACKS[payload]
        st = await add_credits(user_id, credits=pack["credits"], natal=pack.get("natal", False))

        total = sp.total_amount / 100
        natal_txt = "\n🪐 *Натальна карта* відкрита." if pack.get("natal", False) else ""

        await message.answer(
            "✅✨ *Оплату прийнято! Магія активована.* ✨\n\n"
            f"💳 Сума: *{total:.2f} {sp.currency}*\n"
            f"🎴 Нараховано: *{pack['credits']} ворожінь*{natal_txt}\n"
            f"📿 Баланс ворожінь: *{st['credits']}*\n\n"
            "Скажи… з чого почнемо? 🔮",
            parse_mode="Markdown",
            reply_markup=get_main_menu(),
        )
        return

    await message.answer("✅ Оплату отримано. Якщо доступ не активувався — напиши /start.")


# =========================
# BOT LOGIC
# =========================
async def ritual_delay(message: types.Message):
    await message.answer(
        "Зосередься на своєму питанні…\n"
        "Зроби вдих. І ще один.\n"
        "Колода шепоче у темряві… ✨"
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
    natal = bool(st.get("natal", False))

    await message.answer(
        "✨ Я — маг-таролог. Я слухаю твоє питання і читаю знаки… 🧙‍♂️🔮\n\n"
        f"🎁 Безкоштовних ворожінь залишилось: *{free_left}* із {FREE_READINGS}\n"
        f"📿 Платних ворожінь на балансі: *{credits}*\n"
        f"🪐 Натальна карта: *{'доступна' if natal else 'закрита'}*\n\n"
        "Обери ритуал:",
        parse_mode="Markdown",
        reply_markup=get_main_menu(),
    )


@dp.message(Command("disclaimer"))
async def disclaimer_cmd(message: types.Message):
    await message.answer(DISCLAIMER_TEXT, parse_mode="Markdown")


@dp.message(F.text == "📜 Дисклеймер")
async def disclaimer_btn(message: types.Message):
    await message.answer(DISCLAIMER_TEXT, parse_mode="Markdown")


@dp.callback_query(F.data == "show_disclaimer")
async def cb_show_disclaimer(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(DISCLAIMER_TEXT, parse_mode="Markdown")


@dp.message(F.text == "💳 Купити ворожіння")
async def show_paywall(message: types.Message):
    await message.answer(
        "🧙‍♂️💫 *Обери пакунок сили:*",
        parse_mode="Markdown",
        reply_markup=get_paywall_kb(),
    )


@dp.callback_query(F.data == "buy_pack_5")
async def cb_buy_pack_5(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        DISCLAIMER_TEXT + "\n\n✅ Якщо все зрозуміло — можеш продовжити до оплати:",
        parse_mode="Markdown",
        reply_markup=get_disclaimer_confirm_kb("pack_5"),
    )


@dp.callback_query(F.data == "buy_pack_10")
async def cb_buy_pack_10(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        DISCLAIMER_TEXT + "\n\n✅ Якщо все зрозуміло — можеш продовжити до оплати:",
        parse_mode="Markdown",
        reply_markup=get_disclaimer_confirm_kb("pack_10_natal"),
    )


@dp.callback_query(F.data.startswith("confirm_"))
async def cb_confirm_buy(callback: types.CallbackQuery):
    await callback.answer()
    pack_key = callback.data.replace("confirm_", "", 1)
    await send_pack_invoice(chat_id=callback.message.chat.id, pack_key=pack_key)


@dp.callback_query(F.data == "back_menu")
async def cb_back_menu(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("🔙 Повертаю в меню…", reply_markup=get_main_menu())


@dp.message(F.text == "🪐 Натальна карта")
async def natal_chart(message: types.Message):
    st = await get_user_state(message.from_user.id)
    if not st.get("natal", False):
        await message.answer(
            "🪐🔒 *Натальна карта* зараз закрита печаттю зірок.\n\n"
            "Відкрию її тим, хто обере пакунок:\n"
            "🔮 *10 ворожінь + 🪐 Натальна карта* — і я розшифрую твій небесний код ✨",
            parse_mode="Markdown",
            reply_markup=get_paywall_kb(),
        )
        return

    await message.answer(
        "🪐✨ *Натальна карта активна!*\n\n"
        "Наступний крок: я попрошу дату, час і місце народження — і складу інтерпретацію.",
        parse_mode="Markdown",
    )


@dp.message(F.text == "🔮 Одна карта — порада долі")
async def one_card(message: types.Message):
    if not await consume_reading_or_block(message):
        return

    await ritual_delay(message)
    code, orient, path = get_random_card()
    emoji = "✨" if orient == "up" else "🌙"

    caption = (
        f"{emoji} *{NAMES[code]}* {'(пряма)' if orient == 'up' else '(перевернута)'}\n\n"
        f"{MEANINGS[code][orient]}\n\n"
        "Дихай. Відповідь уже поруч."
    )

    if os.path.exists(path):
        await message.answer_photo(FSInputFile(path), caption=caption, parse_mode="Markdown")
    else:
        await message.answer(caption, parse_mode="Markdown")


@dp.message(F.text == "🃏 Три карти — шлях душі")
async def three_cards(message: types.Message):
    if not await consume_reading_or_block(message):
        return

    await ritual_delay(message)

    cards = [get_random_card() for _ in range(3)]
    media = []
    text = "*Три карти — шлях душі*\n\n"
    positions = ["🕰 Минуле", "🌟 Теперішнє", "🔮 Майбутнє"]

    for i, (code, orient, path) in enumerate(cards):
        emoji = "✨" if orient == "up" else "🌙"
        text += (
            f"{positions[i]}\n"
            f"{emoji} *{NAMES[code]}* {'(пряма)' if orient == 'up' else '(перевернута)'}\n"
            f"{MEANINGS[code][orient]}\n\n"
        )
        if os.path.exists(path):
            media.append(types.InputMediaPhoto(media=FSInputFile(path)))

    if media:
        await message.answer_media_group(media)

    await message.answer(text + "Три нитки сплелись… шлях уже змінюється ✨", parse_mode="Markdown")


@dp.message(F.text == "✨ Кельтський хрест — повне ворожіння")
async def celtic_cross(message: types.Message):
    if not await consume_reading_or_block(message):
        return

    await ritual_delay(message)
    await message.answer(
        "*Кельтський хрест*\n\n"
        "Невдовзі тут буде повний розклад на 10 карт. А поки — відчуй енергію розкладу ✨",
        parse_mode="Markdown",
    )


@dp.message(F.text == "❓ Так / Ні — швидка відповідь")
async def yes_no(message: types.Message):
    if not await consume_reading_or_block(message):
        return

    await ritual_delay(message)
    answers = [
        "✅ Так. Аркани говорять чітко.",
        "❌ Ні. Двері зараз зачинені — не ламай їх.",
        "❓ Можливо. Якщо зміниш курс — шанс з’явиться.",
    ]
    await message.answer(random.choice(answers))


async def main():
    await load_state()
    print("🧙‍♂️ Бот готовий до ритуалу…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
