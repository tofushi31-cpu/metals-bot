"""Тг-бот с зонами интереса (уровни Фибоначчи) по золоту/серебру/меди/алюминию.

Только для личного использования — отвечает и шлёт дайджест только ADMIN_IDS.
Не финансовый совет: сырые уровни цены, решение принимает человек.
"""

import asyncio
import logging
import os
import tempfile
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from dotenv import load_dotenv

import sheets
from captions import format_metal_caption, format_zone_alert
from chart import render_chart
from history import (
    active_subscribers,
    add_subscription,
    is_subscriber,
    record_alert,
    was_alerted_today,
)
from signals import FIB_LABELS, METALS, compute_fib_zones, fetch_prices

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "9"))  # во сколько присылать ежедневный дайджест
DIGEST_TZ = ZoneInfo(os.getenv("DIGEST_TZ", "Asia/Almaty"))  # таймзона дайджеста
ALERT_INTERVAL_MIN = int(os.getenv("ALERT_INTERVAL_MIN", "30"))  # как часто проверять зоны
STARS_PRICE = int(os.getenv("STARS_PRICE", "100"))  # цена подписки в Telegram Stars
SUB_DAYS = int(os.getenv("SUB_DAYS", "30"))  # длительность подписки в днях

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def has_access(user_id: int) -> bool:
    return is_admin(user_id) or is_subscriber(user_id)


def recipients() -> set[int]:
    """Кому слать дайджест и алерты: админы + активные подписчики."""
    return ADMIN_IDS | set(active_subscribers())


async def ack(callback: CallbackQuery, text: str | None = None):
    """Ответ на callback; после рестарта бота query может протухнуть (>48с) —
    это не повод не отправлять сам график."""
    try:
        await callback.answer(text)
    except TelegramBadRequest:
        pass


_metal_buttons = [
    InlineKeyboardButton(text=name, callback_data=f"metal:{name}") for name in METALS
]
main_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        *[_metal_buttons[i : i + 2] for i in range(0, len(_metal_buttons), 2)],
        [InlineKeyboardButton(text="📊 Все металлы", callback_data="metal:all")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
    ]
)

HELP_TEXT = (
    "Уровни коррекции Фибоначчи — по максимуму и минимуму цены за последние "
    "60 дней строится диапазон, внутри него отмечаются уровни:\n"
    "  0% и 100% — сам максимум и минимум диапазона\n"
    "  23.6%, 38.2%, 50%, 78.6% — промежуточные уровни\n"
    "  61.8% — золотое сечение, обычно самый значимый уровень\n\n"
    "Ближайший к текущей цене уровень помечен 'ближайший', а если цена подошла "
    "к нему ближе чем на 1% — 'в зоне', то есть в зону интереса для возможного "
    "входа или выхода.\n\n"
    "Это просто уровни цены, не рекомендация покупать/продавать."
)


async def send_metal(chat_id: int, name: str):
    ticker = METALS[name]
    try:
        df = await asyncio.to_thread(fetch_prices, ticker)
    except Exception:
        logging.exception("Не удалось получить данные для %s", name)
        await bot.send_message(chat_id, f"{name}: данные сейчас недоступны, попробуй позже.")
        return
    zones = compute_fib_zones(df)
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "chart.png")
        render_chart(df, zones, name, path)
        await bot.send_photo(
            chat_id, FSInputFile(path), caption=format_metal_caption(name, zones)
        )


async def send_all_metals(chat_id: int):
    for name in METALS:
        await send_metal(chat_id, name)


subscribe_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Подписка — {STARS_PRICE} Stars / {SUB_DAYS} дней", callback_data="subscribe")],
        [InlineKeyboardButton(text="❓ Что я получу", callback_data="help")],
    ]
)

INSTRUMENTS_TEXT = "золотом, серебром, медью, алюминием и нефтью Brent"


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if has_access(message.from_user.id):
        await message.answer(
            f"Слежу за {INSTRUMENTS_TEXT}.\n\n"
            f"Присылаю дайджест каждый день около {DIGEST_HOUR}:00 и алерты, "
            "когда цена входит в зону Фибоначчи.\n\n"
            "Выбери, что показать:",
            reply_markup=main_menu,
        )
    else:
        await message.answer(
            f"Слежу за {INSTRUMENTS_TEXT}: свечные графики с уровнями Фибоначчи, "
            "ежедневный дайджест и алерты, когда цена входит в зону интереса.\n\n"
            "Не финансовый совет — сырые уровни цены.\n\n"
            "Доступ по подписке:",
            reply_markup=subscribe_menu,
        )


@dp.callback_query(lambda c: c.data == "subscribe")
async def cb_subscribe(callback: CallbackQuery):
    await ack(callback)
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="Подписка на зоны Фибоначчи",
        description=(
            f"Дайджест и алерты по {INSTRUMENTS_TEXT} на {SUB_DAYS} дней. "
            "Не финансовый совет."
        ),
        payload="fib-subscription",
        currency="XTR",  # Telegram Stars, платёжный провайдер не нужен
        prices=[LabeledPrice(label=f"Подписка {SUB_DAYS} дней", amount=STARS_PRICE)],
    )


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_payment(message: Message):
    expires = add_subscription(message.from_user.id, SUB_DAYS)
    logging.info(
        "Оплата: user=%s, %s XTR, подписка до %s",
        message.from_user.id, message.successful_payment.total_amount, expires,
    )
    await message.answer(
        f"Спасибо! Подписка активна до {expires[:10]}.\n\n"
        "Теперь тебе доступны графики, дайджест и алерты:",
        reply_markup=main_menu,
    )


@dp.callback_query(lambda c: c.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.answer(HELP_TEXT)
    await ack(callback)


@dp.callback_query(lambda c: c.data == "metal:all")
async def cb_metal_all(callback: CallbackQuery):
    if not has_access(callback.from_user.id):
        return
    await ack(callback, "Собираю графики...")
    await send_all_metals(callback.message.chat.id)


@dp.callback_query(lambda c: c.data.startswith("metal:"))
async def cb_metal_one(callback: CallbackQuery):
    if not has_access(callback.from_user.id):
        return
    name = callback.data.split(":", 1)[1]
    if name not in METALS:
        return
    await ack(callback, "Собираю график...")
    await send_metal(callback.message.chat.id, name)


async def daily_digest_loop():
    while True:
        now = datetime.now(DIGEST_TZ)
        target = datetime.combine(now.date(), time(hour=DIGEST_HOUR), tzinfo=DIGEST_TZ)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        for chat_id in recipients():
            try:
                await send_all_metals(chat_id)
            except Exception:
                logging.exception("Дайджест для %s не отправился", chat_id)


async def zone_alert_loop():
    """Каждые ALERT_INTERVAL_MIN минут проверяет, не вошла ли цена в зону Фибоначчи.
    Один алерт на металл+уровень в день (дедупликация в metals.db)."""
    while True:
        for name, ticker in METALS.items():
            try:
                df = await asyncio.to_thread(fetch_prices, ticker)
            except Exception:
                logging.exception("Алерт-проверка %s: данные недоступны", name)
                continue
            zones = compute_fib_zones(df)
            if not zones["near_zone"] or was_alerted_today(name, zones["nearest_ratio"]):
                continue
            record_alert(name, zones["nearest_ratio"], zones["current_price"])
            await asyncio.to_thread(
                sheets.export_alert,
                name,
                FIB_LABELS[zones["nearest_ratio"]],
                zones["nearest_level"],
                zones["current_price"],
            )
            for chat_id in recipients():
                try:
                    await bot.send_message(chat_id, format_zone_alert(name, zones))
                except Exception:
                    logging.exception("Алерт %s для %s не отправился", name, chat_id)
        await asyncio.sleep(ALERT_INTERVAL_MIN * 60)


async def main():
    asyncio.create_task(daily_digest_loop())
    asyncio.create_task(zone_alert_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
