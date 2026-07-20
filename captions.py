"""Текстовые подписи к графикам — вынесены из bot.py, чтобы тестировать без токена."""

from signals import DIVERGENCE_LABELS, FIB_LABELS

DIVERGENCE_ICONS = {
    "classic_bullish": "🟢",
    "classic_bearish": "🔴",
    "hidden_bullish": "🟢",
    "hidden_bearish": "🔴",
}


def _divergence_line(divergences: list[dict] | None) -> str | None:
    if not divergences:
        return None
    parts = [f"{DIVERGENCE_ICONS[d['type']]} {DIVERGENCE_LABELS[d['type']]}" for d in divergences]
    return "🔀 Дивергенция: " + ", ".join(parts)

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
    "Нефть Brent": "BRN1! (ICE Brent Crude Futures)",
}


def format_metal_caption(
    name: str,
    z: dict,
    tf_label: str = "дневные свечи",
    paused: bool = False,
    divergences: list[dict] | None = None,
    candles: int = 60,
) -> str:
    """Подпись к графику (HTML): жирный заголовок, уровни ровным столбиком."""
    lines = [
        f"<b>{name}</b> — цена <b>{z['current_price']}</b> · {tf_label}",
        f"Диапазон последних {candles} свечей: {z['low']}–{z['high']}",
        "",
    ]
    if paused:
        lines.insert(
            2,
            "⏸ <i>Рынок сейчас закрыт (выходные или перерыв) — показаны последние "
            "доступные свечи, новые появятся после открытия торгов.</i>",
        )
    div_line = _divergence_line(divergences)
    if div_line:
        lines.insert(-1, div_line)
    level_rows = []
    for ratio, level in z["levels"].items():
        star = "★" if ratio == 0.618 else " "
        marker = (
            "  🎯 в зоне" if ratio == z["nearest_ratio"] and z["near_zone"]
            else "  ← ближайший" if ratio == z["nearest_ratio"]
            else ""
        )
        level_rows.append(f"{ratio * 100:>5.1f}%{star} {level:>10}{marker}")
    lines.append("<code>" + "\n".join(level_rows) + "</code>")
    lines += [
        "",
        "★ — золотое сечение, обычно самый значимый уровень",
        f"<i>Искать в терминале: {TERMINAL_SEARCH[name]}</i>",
    ]
    return "\n".join(lines)


def format_zone_alert(name: str, z: dict, divergences: list[dict] | None = None) -> str:
    div_line = _divergence_line(divergences)
    div_part = f"{div_line}\n" if div_line else ""
    return (
        f"⚡ <b>{name}</b>: цена <b>{z['current_price']}</b> вошла в зону уровня "
        f"<b>{FIB_LABELS[z['nearest_ratio']]}</b> ({z['nearest_level']}).\n"
        f"Диапазон свинга: {z['low']}–{z['high']}.\n"
        f"{div_part}"
        f"<i>Не финансовый совет.</i>"
    )


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def format_stats(rows: list[dict]) -> str:
    """Сводка /stats: среднее движение цены после входа в зону. Честно про малую
    выборку — выводы по паре сигналов делать нельзя."""
    if not rows:
        return (
            "<b>📈 Статистика сигналов</b>\n\n"
            "Пока пустая: она копится с каждым алертом.\n"
            "Загляни через несколько недель."
        )
    lines = [
        "<b>📈 Статистика сигналов</b>",
        "Средний ход цены после входа в зону (1д / 3д / 7д):",
        "",
    ]
    for r in rows:
        lines.append(
            f"<b>{r['metal']} {FIB_LABELS[r['ratio']]}</b> — сигналов {r['signals']}:\n"
            f"    {_fmt_pct(r['avg_1d'])} / {_fmt_pct(r['avg_3d'])} / {_fmt_pct(r['avg_7d'])}"
        )
    lines += [
        "",
        "<i>Это не вероятность успеха, а среднее движение цены. "
        "Пока сигналов мало, цифры шумные. Не финансовый совет.</i>",
    ]
    return "\n".join(lines)
