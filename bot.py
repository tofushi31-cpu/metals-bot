"""Тг-бот с зонами интереса (уровни Фибоначчи) по золоту/серебру/меди/алюминию.

Только для личного использования — отвечает и шлёт дайджест только ADMIN_IDS.
Не финансовый совет: сырые уровни цены, решение принимает человек.
"""

import asyncio
import logging
import os
import tempfile
from datetime import datetime, time, timedelta

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

from chart import render_metal_chart
from signals import FIB_LABELS, METALS, compute_fib_zones, fetch_prices

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "9"))  # во сколько присылать ежедневный дайджест, локальное время сервера

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


main_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"metal:{name}") for name in METALS][:2],
        [InlineKeyboardButton(text=name, callback_data=f"metal:{name}") for name in METALS][2:],
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


# Как искать инструмент на TradingView (поиск сверху, ввести этот код).
# Подтверждено через официальные страницы контрактов TradingView.
TERMINAL_SEARCH = {
    "Золото": "GC1! (COMEX Gold Futures)",
    "Серебро": "SI1! (COMEX Silver Futures)",
    "Медь": "HG1! (COMEX Copper Futures)",
    # для алюминия два варианта: ALI1! точно совпадает с источником данных бота
    # (Yahoo ALI=F), но малоликвиден; AH1! — основной мировой бенчмарк (LME),
    # цифры будут немного отличаться от того, что считает бот
    "Алюминий": "ALI1! (COMEX, совпадает с данными бота) или AH1! (LME, более ликвидный бенчмарк)",
}


def format_metal_caption(name: str, z: dict) -> str:
    lines = [f"{name}: цена {z['current_price']} (диапазон {z['low']}-{z['high']})", ""]
    for ratio, level in z["levels"].items():
        marker = (
            " <- ближайший, в зоне" if ratio == z["nearest_ratio"] and z["near_zone"]
            else " <- ближайший" if ratio == z["nearest_ratio"]
            else ""
        )
        lines.append(f"{FIB_LABELS[ratio]}: {level}{marker}")
    lines += ["", f"Искать в терминале: {TERMINAL_SEARCH[name]}"]
    return "\n".join(lines)


async def send_metal(chat_id: int, name: str):
    ticker = METALS[name]
    df = fetch_prices(ticker)
    zones = compute_fib_zones(df)
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "chart.png")
        render_metal_chart(name, ticker, path)
        await bot.send_photo(
            chat_id, FSInputFile(path), caption=format_metal_caption(name, zones)
        )


async def send_all_metals(chat_id: int):
    for name in METALS:
        await send_metal(chat_id, name)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Слежу за золотом, серебром, медью и алюминием.\n\n"
        f"Плюс присылаю дайджест сам каждый день около {DIGEST_HOUR}:00.\n\n"
        "Выбери, что показать:",
        reply_markup=main_menu,
    )


@dp.callback_query(lambda c: c.data == "help")
async def cb_help(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.answer(HELP_TEXT)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "metal:all")
async def cb_metal_all(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Собираю графики...")
    await send_all_metals(callback.message.chat.id)


@dp.callback_query(lambda c: c.data.startswith("metal:"))
async def cb_metal_one(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    name = callback.data.split(":", 1)[1]
    if name not in METALS:
        return
    await callback.answer("Собираю график...")
    await send_metal(callback.message.chat.id, name)


async def daily_digest_loop():
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), time(hour=DIGEST_HOUR))
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        for admin_id in ADMIN_IDS:
            await send_all_metals(admin_id)


async def main():
    asyncio.create_task(daily_digest_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
