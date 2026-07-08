"""Тг-бот с зонами интереса (уровни Фибоначчи) по золоту/серебру/меди/алюминию.

Только для личного использования — отвечает и шлёт дайджест только ADMIN_IDS.
Не финансовый совет: сырые уровни цены, решение принимает человек.
"""

import asyncio
import logging
import os
from datetime import datetime, time, timedelta

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from signals import FIB_LABELS, check_all_fib_zones

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "9"))  # во сколько присылать ежедневный дайджест, локальное время сервера

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def format_digest() -> str:
    results = check_all_fib_zones()
    lines = [f"Зоны интереса на {datetime.now():%d.%m.%Y}", ""]
    for metal, z in results.items():
        nearest_label = FIB_LABELS[z["nearest_ratio"]]
        marker = " <- в зоне" if z["near_zone"] else ""
        lines.append(
            f"{metal}: цена {z['current_price']} (диапазон {z['low']}-{z['high']})\n"
            f"  ближайший уровень {nearest_label} = {z['nearest_level']}{marker}"
        )
    lines += ["", "Не финансовый совет — сырые уровни цены, решение за тобой."]
    return "\n".join(lines)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Слежу за золотом, серебром, медью и алюминием.\n\n"
        "/signals — сигналы прямо сейчас\n"
        "/help — что означают цифры\n\n"
        f"Плюс присылаю то же самое каждый день около {DIGEST_HOUR}:00 без запроса."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Уровни коррекции Фибоначчи — по максимуму и минимуму цены за последние "
        "60 дней строится диапазон, внутри него отмечаются уровни:\n"
        "  0% и 100% — сам максимум и минимум диапазона\n"
        "  23.6%, 38.2%, 50%, 78.6% — промежуточные уровни\n"
        "  61.8% — золотое сечение, обычно самый значимый уровень\n\n"
        "Бот показывает ближайший к текущей цене уровень и помечает 'в зоне', "
        "если цена подошла к нему ближе чем на 1% — то есть в зону интереса "
        "для возможного входа или выхода.\n\n"
        "Это просто уровни цены, не рекомендация покупать/продавать."
    )


@dp.message(Command("signals"))
async def cmd_signals(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(format_digest())


async def daily_digest_loop():
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), time(hour=DIGEST_HOUR))
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        digest = format_digest()
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, digest)


async def main():
    asyncio.create_task(daily_digest_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
