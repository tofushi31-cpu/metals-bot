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
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

import sheets
from captions import format_metal_caption, format_stats, format_zone_alert
from chart import render_chart
from history import (
    active_subscribers,
    add_subscription,
    alerts_missing_outcomes,
    create_gift,
    is_subscriber,
    level_stats,
    record_alert,
    record_outcome,
    redeem_gift,
    was_alerted_today,
)
from signals import (
    ALGO_VERSION,
    DEFAULT_TIMEFRAME,
    FIB_LABELS,
    METALS,
    TIMEFRAME_TITLES,
    TIMEFRAMES,
    close_price_after,
    compute_fib_zones,
    compute_indicators,
    fetch_prices,
    fetch_timeframe,
)

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


async def notify_admins(text: str):
    """Служебное уведомление всем админам (новый подписчик и т.п.)."""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logging.exception("Уведомление админу %s не отправилось", admin_id)


def user_label(user) -> str:
    parts = [user.full_name or "без имени"]
    if user.username:
        parts.append(f"@{user.username}")
    parts.append(f"id {user.id}")
    return ", ".join(parts)


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
        [InlineKeyboardButton(text="📈 Статистика сигналов", callback_data="stats")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
    ]
)


# Постоянная клавиатура внизу экрана — всегда под рукой, не исчезает после нажатия
BTN_CHARTS = "📊 Графики"
BTN_STATS = "📈 Статистика"
BTN_HELP = "❓ Помощь"
bottom_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_CHARTS), KeyboardButton(text=BTN_STATS)],
        [KeyboardButton(text=BTN_HELP)],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def alert_menu(name: str) -> InlineKeyboardMarkup:
    """Кнопки под алертом: сразу открыть график инструмента или главное меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 График", callback_data=f"metal:{name}"),
                InlineKeyboardButton(text="📋 Меню", callback_data="menu"),
            ]
        ]
    )

HELP_TEXT = (
    "<b>📐 Уровни Фибоначчи</b>\n\n"
    "Уровни коррекции Фибоначчи — по максимуму и минимуму цены за последние "
    "60 свечей выбранного таймфрейма (для дневного — 60 дней) строится "
    "диапазон, внутри него отмечаются уровни:\n"
    "  0% и 100% — сам максимум и минимум диапазона\n"
    "  23.6%, 38.2%, 50%, 78.6% — промежуточные уровни\n"
    "  61.8% — золотое сечение, обычно самый значимый уровень\n\n"
    "Ближайший к текущей цене уровень помечен 'ближайший', а если цена подошла "
    "к нему ближе чем на 1% — 'в зоне', то есть в зону интереса для возможного "
    "входа или выхода.\n\n"
    "Это просто уровни цены, не рекомендация покупать/продавать."
)

STATS_HELP_TEXT = (
    "<b>📈 Как читать статистику</b>\n\n"
    "Каждый раз, когда цена входит в зону уровня, бот записывает сигнал, "
    "а потом смотрит, куда цена ушла через 1, 3 и 7 дней.\n\n"
    "<b>Пример строки:</b>\n"
    "<code>Золото 61.8%: сигналов 5, +1.2% / -0.5% / +2.0%</code>\n\n"
    "Это значит: таких сигналов было 5, и в среднем через день после сигнала "
    "цена была на 1.2% выше, через 3 дня — на 0.5% ниже, через неделю — "
    "на 2% выше. Плюс — цена в среднем росла, минус — падала, "
    "прочерк — результат ещё не наступил.\n\n"
    "<b>Зачем это нужно:</b> со временем видно, какие уровни у каких "
    "инструментов реально отрабатывают, а какие — просто шум.\n\n"
    "<b>Важно:</b> это среднее по прошлому, а не гарантия на будущее. "
    "Пока сигналов по уровню меньше 20-30, цифры шумные и выводы делать рано. "
    "Не финансовый совет."
)

USAGE_TEXT = (
    "<b>🤖 Как пользоваться ботом</b>\n\n"
    "<b>📊 Графики</b> — свечной график любого инструмента с уровнями Фибоначчи "
    "и RSI, в подписи — все уровни и ближайший к цене. Под графиком — кнопки "
    "таймфреймов: от 15 минут до недели, по умолчанию дневной. Уровни "
    "пересчитываются под выбранный таймфрейм.\n\n"
    "Алерты, дайджест и статистика всегда считаются по дневному таймфрейму.\n\n"
    "<b>📈 Статистика</b> — как отрабатывали прошлые сигналы (см. раздел "
    "«Как читать статистику»).\n\n"
    "Каждое утро бот сам присылает дайджест — графики всех инструментов. "
    "А когда цена входит в зону уровня — присылает алерт, под ним кнопка "
    "«График», чтобы сразу посмотреть картину.\n\n"
    "Ничего настраивать не нужно: подписка активна — значит дайджест "
    "и алерты уже приходят."
)

help_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📐 Уровни Фибоначчи", callback_data="help:fib")],
        [InlineKeyboardButton(text="📈 Как читать статистику", callback_data="help:stats")],
        [InlineKeyboardButton(text="🤖 Как пользоваться ботом", callback_data="help:usage")],
    ]
)

stats_help_button = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="❓ Как читать", callback_data="help:stats")]
    ]
)


def tf_menu(name: str, current: str) -> InlineKeyboardMarkup:
    """Кнопки таймфреймов под графиком; текущий помечен точкой."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"• {tf}" if tf == current else tf,
                    callback_data=f"tf:{name}:{tf}",
                )
                for tf in TIMEFRAMES
            ]
        ]
    )


async def send_metal(chat_id: int, name: str, tf: str = DEFAULT_TIMEFRAME):
    ticker = METALS[name]
    try:
        df = await asyncio.to_thread(fetch_timeframe, ticker, tf)
    except Exception:
        logging.exception("Не удалось получить данные для %s (%s)", name, tf)
        await bot.send_message(chat_id, f"{name}: данные сейчас недоступны, попробуй позже.")
        return
    zones = compute_fib_zones(df)
    tf_label = TIMEFRAME_TITLES[tf]
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "chart.png")
        render_chart(df, zones, name, path, tf_label=tf_label)
        await bot.send_photo(
            chat_id,
            FSInputFile(path),
            caption=format_metal_caption(name, zones, tf_label),
            parse_mode="HTML",
            reply_markup=tf_menu(name, tf),
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
async def cmd_start(message: Message, command: CommandObject):
    # Переход по подарочной ссылке: /start gift_<код>
    if command.args and command.args.startswith("gift_"):
        days = redeem_gift(command.args.removeprefix("gift_"), message.from_user.id)
        if days:
            expires = add_subscription(message.from_user.id, days)
            await message.answer(
                f"🎁 Тебе подарили подписку на {days} дней — активна до {expires[:10]}.\n\n"
                f"Слежу за {INSTRUMENTS_TEXT}: графики, ежедневный дайджест и алерты.\n"
                "Кнопки навигации — внизу экрана 👇",
                reply_markup=bottom_keyboard,
            )
            await notify_admins(
                f"🎁 По подарочной ссылке подписался: {user_label(message.from_user)}. "
                f"Подписка на {days} дней, до {expires[:10]}."
            )
            await asyncio.to_thread(
                sheets.export_subscription,
                "подарок",
                user_label(message.from_user),
                days,
                expires[:10],
            )
            return
        await message.answer("Эта подарочная ссылка уже использована или недействительна.")

    if has_access(message.from_user.id):
        await message.answer(
            f"Слежу за {INSTRUMENTS_TEXT}.\n\n"
            f"Присылаю дайджест каждый день около {DIGEST_HOUR}:00 и алерты, "
            "когда цена входит в зону Фибоначчи.\n\n"
            "Кнопки навигации — внизу экрана 👇",
            reply_markup=bottom_keyboard,
        )
    else:
        await message.answer(
            f"Слежу за {INSTRUMENTS_TEXT}: свечные графики с уровнями Фибоначчи, "
            "ежедневный дайджест и алерты, когда цена входит в зону интереса.\n\n"
            "Не финансовый совет — сырые уровни цены.\n\n"
            "Доступ по подписке:",
            reply_markup=subscribe_menu,
        )


@dp.message(Command("gift"))
async def cmd_gift(message: Message, command: CommandObject):
    """Только для админов: /gift [дней] — одноразовая подарочная ссылка на подписку."""
    if not is_admin(message.from_user.id):
        return
    args = (command.args or "").strip()
    days = int(args) if args.isdigit() and int(args) > 0 else SUB_DAYS
    code = create_gift(days)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=gift_{code}"
    await message.answer(
        f"🎁 Подарочная ссылка на <b>{days} дней</b> подписки:\n\n"
        f"{link}\n\n"
        "Отправь её тому, кому даришь. Ссылка одноразовая — сработает "
        "только у первого, кто по ней перейдёт и нажмёт Start.\n"
        f"<i>Другой срок: /gift 90 — ссылка на 90 дней.</i>",
        parse_mode="HTML",
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
        "Теперь тебе доступны графики, дайджест и алерты — "
        "кнопки навигации внизу экрана 👇",
        reply_markup=bottom_keyboard,
    )
    await notify_admins(
        f"⭐ Новая оплата: {user_label(message.from_user)}. "
        f"{message.successful_payment.total_amount} XTR, подписка до {expires[:10]}."
    )
    await asyncio.to_thread(
        sheets.export_subscription,
        "оплата Stars",
        user_label(message.from_user),
        SUB_DAYS,
        expires[:10],
    )


@dp.callback_query(lambda c: c.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.answer("Что объяснить?", reply_markup=help_menu)
    await ack(callback)


HELP_SECTIONS = {
    "help:fib": HELP_TEXT,
    "help:stats": STATS_HELP_TEXT,
    "help:usage": USAGE_TEXT,
}


@dp.callback_query(lambda c: c.data in HELP_SECTIONS)
async def cb_help_section(callback: CallbackQuery):
    await callback.message.answer(HELP_SECTIONS[callback.data], parse_mode="HTML")
    await ack(callback)


@dp.callback_query(lambda c: c.data == "menu")
async def cb_menu(callback: CallbackQuery):
    await ack(callback)
    if has_access(callback.from_user.id):
        await callback.message.answer("Выбери, что показать:", reply_markup=main_menu)
    else:
        await callback.message.answer("Доступ по подписке:", reply_markup=subscribe_menu)


@dp.callback_query(lambda c: c.data == "stats")
async def cb_stats(callback: CallbackQuery):
    if not has_access(callback.from_user.id):
        return
    await ack(callback)
    stats = await asyncio.to_thread(level_stats)
    await callback.message.answer(
        format_stats(stats), reply_markup=stats_help_button, parse_mode="HTML"
    )


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


@dp.callback_query(lambda c: c.data.startswith("tf:"))
async def cb_timeframe(callback: CallbackQuery):
    if not has_access(callback.from_user.id):
        return
    _, name, tf = callback.data.split(":", 2)
    if name not in METALS or tf not in TIMEFRAMES:
        return
    await ack(callback, "Собираю график...")
    await send_metal(callback.message.chat.id, name, tf)


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not has_access(message.from_user.id):
        return
    stats = await asyncio.to_thread(level_stats)
    await message.answer(
        format_stats(stats), reply_markup=stats_help_button, parse_mode="HTML"
    )


@dp.message(F.text == BTN_CHARTS)
async def btn_charts(message: Message):
    if not has_access(message.from_user.id):
        await message.answer("Доступ по подписке:", reply_markup=subscribe_menu)
        return
    await message.answer("Выбери, что показать:", reply_markup=main_menu)


@dp.message(F.text == BTN_STATS)
async def btn_stats(message: Message):
    if not has_access(message.from_user.id):
        await message.answer("Доступ по подписке:", reply_markup=subscribe_menu)
        return
    stats = await asyncio.to_thread(level_stats)
    await message.answer(
        format_stats(stats), reply_markup=stats_help_button, parse_mode="HTML"
    )


@dp.message(F.text == BTN_HELP)
async def btn_help(message: Message):
    await message.answer("Что объяснить?", reply_markup=help_menu)


@dp.message()
async def any_text(message: Message):
    """Фолбэк: на любое сообщение возвращаем навигацию, чтобы она была всегда
    под рукой, а не только после /start. Регистрируется последним."""
    if has_access(message.from_user.id):
        await message.answer("Кнопки навигации — внизу экрана 👇", reply_markup=bottom_keyboard)
    else:
        await message.answer("Доступ по подписке:", reply_markup=subscribe_menu)


async def outcome_backfill_loop():
    """Раз в сутки дописывает к старым алертам цену через 1/3/7 дней —
    из этого копится статистика отработки уровней (/stats)."""
    while True:
        for name, ticker in METALS.items():
            try:
                pending = await asyncio.to_thread(alerts_missing_outcomes, name)
                if not pending:
                    continue
                df = await asyncio.to_thread(fetch_prices, ticker)
                for alert in pending:
                    for horizon in alert["missing"]:
                        price = close_price_after(df, alert["day"], horizon)
                        if price is not None:
                            await asyncio.to_thread(
                                record_outcome, alert["id"], horizon, price
                            )
            except Exception:
                logging.exception("Дозапись результатов %s не удалась", name)
        await asyncio.sleep(24 * 60 * 60)


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
                zones = compute_fib_zones(df)
            except Exception:
                logging.exception("Алерт-проверка %s не удалась", name)
                continue
            if not zones["near_zone"] or was_alerted_today(name, zones["nearest_ratio"]):
                continue
            indicators = compute_indicators(df)
            record_alert(
                name,
                zones["nearest_ratio"],
                zones["current_price"],
                rsi=indicators["rsi"],
                atr=indicators["atr"],
                algo_version=ALGO_VERSION,
            )
            await asyncio.to_thread(
                sheets.export_alert,
                name,
                FIB_LABELS[zones["nearest_ratio"]],
                zones["nearest_level"],
                zones["current_price"],
            )
            for chat_id in recipients():
                try:
                    await bot.send_message(
                        chat_id,
                        format_zone_alert(name, zones),
                        reply_markup=alert_menu(name),
                        parse_mode="HTML",
                    )
                except Exception:
                    logging.exception("Алерт %s для %s не отправился", name, chat_id)
        await asyncio.sleep(ALERT_INTERVAL_MIN * 60)


async def main():
    public_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="stats", description="Статистика сигналов"),
    ]
    await bot.set_my_commands(public_commands)
    admin_commands = public_commands + [
        BotCommand(command="gift", description="Подарить подписку (ссылкой)"),
    ]
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                admin_commands, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except TelegramBadRequest:
            # админ ещё ни разу не открывал чат с ботом — некуда ставить меню
            logging.warning("Не удалось задать меню команд для админа %s", admin_id)
    asyncio.create_task(daily_digest_loop())
    asyncio.create_task(zone_alert_loop())
    asyncio.create_task(outcome_backfill_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
