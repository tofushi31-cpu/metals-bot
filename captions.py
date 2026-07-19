"""Текстовые подписи к графикам — вынесены из bot.py, чтобы тестировать без токена."""

from signals import FIB_LABELS

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


def format_zone_alert(name: str, z: dict) -> str:
    return (
        f"⚡ {name}: цена {z['current_price']} вошла в зону "
        f"{FIB_LABELS[z['nearest_ratio']]} (уровень {z['nearest_level']}).\n"
        f"Диапазон свинга: {z['low']}-{z['high']}. Не финансовый совет."
    )


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def format_stats(rows: list[dict]) -> str:
    """Сводка /stats: среднее движение цены после входа в зону. Честно про малую
    выборку — выводы по паре сигналов делать нельзя."""
    if not rows:
        return (
            "Статистика пока пустая: она копится с каждым алертом.\n"
            "Загляни через несколько недель."
        )
    lines = ["Средний ход цены после входа в зону (за 1д / 3д / 7д):", ""]
    for r in rows:
        lines.append(
            f"{r['metal']} {FIB_LABELS[r['ratio']]}: сигналов {r['signals']}, "
            f"{_fmt_pct(r['avg_1d'])} / {_fmt_pct(r['avg_3d'])} / {_fmt_pct(r['avg_7d'])}"
        )
    lines += [
        "",
        "Это не вероятность успеха, а среднее движение цены. "
        "Пока сигналов мало, цифры шумные. Не финансовый совет.",
    ]
    return "\n".join(lines)
