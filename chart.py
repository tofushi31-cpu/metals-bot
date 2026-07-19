"""Свечной график с зонами Фибоначчи и RSI — рендерится в PNG для отправки в Telegram.

Бесплатно, без TradingView: mplfinance поверх тех же данных yfinance,
что использует signals.py.
"""

import matplotlib.pyplot as plt
import pandas as pd
import pandas_ta  # noqa: F401 — регистрирует аксессор df.ta
import mplfinance as mpf

GOLDEN_RATIO = 0.618

# Линия дивергенции на графике: цвет по направлению, штрих по типу
DIVERGENCE_STYLE = {
    "classic_bullish": dict(color="limegreen", linestyle="-"),
    "classic_bearish": dict(color="crimson", linestyle="-"),
    "hidden_bullish": dict(color="limegreen", linestyle="--"),
    "hidden_bearish": dict(color="crimson", linestyle="--"),
}
DIVERGENCE_SHORT_LABELS = {
    "classic_bullish": "класс. ▲",
    "classic_bearish": "класс. ▼",
    "hidden_bullish": "скрытая ▲",
    "hidden_bearish": "скрытая ▼",
}


def render_chart(
    df: pd.DataFrame,
    zones: dict,
    metal_name: str,
    out_path: str,
    tf_label: str = "дневные свечи",
    divergences: list[dict] | None = None,
) -> str:
    df = df.copy()
    df.ta.rsi(length=14, append=True)

    levels = zones["levels"]
    hline_values = list(levels.values())
    hline_colors = [
        "goldenrod" if ratio == GOLDEN_RATIO else "gray" for ratio in levels
    ]
    hline_widths = [2.2 if ratio == GOLDEN_RATIO else 1 for ratio in levels]

    rsi_panel = mpf.make_addplot(df["RSI_14"], panel=1, ylabel="RSI", color="steelblue")

    fig, axes = mpf.plot(
        df,
        type="candle",
        style="charles",
        title=f"\n{metal_name} — зоны Фибоначчи ({tf_label})",
        hlines=dict(hlines=hline_values, colors=hline_colors, linewidths=hline_widths, linestyle="--"),
        addplot=[rsi_panel],
        panel_ratios=(3, 1),
        volume=False,
        figsize=(10, 7),
        returnfig=True,
    )

    # Линии дивергенции: соединяем два перелома на цене и те же точки на RSI —
    # axes[0] основная цена, axes[2] панель RSI (mplfinance отдаёт по 2 оси на панель)
    price_ax, rsi_ax = axes[0], axes[2]
    for div in divergences or []:
        try:
            x1, x2 = df.index.get_loc(div["date1"]), df.index.get_loc(div["date2"])
        except KeyError:
            continue  # дата перелома не попала в обрезанный для графика диапазон
        style = DIVERGENCE_STYLE[div["type"]]
        for ax, y1, y2 in ((price_ax, div["price1"], div["price2"]), (rsi_ax, div["rsi1"], div["rsi2"])):
            ax.plot([x1, x2], [y1, y2], marker="o", markersize=4, linewidth=1.8, zorder=5, **style)
        price_ax.annotate(
            DIVERGENCE_SHORT_LABELS[div["type"]],
            xy=(x2, div["price2"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=7,
            fontweight="bold",
            color=style["color"],
        )

    # Подпись каждого уровня слева на самой линии: "61.8% · 4269.13"
    for ratio, level in levels.items():
        is_golden = ratio == GOLDEN_RATIO
        price_ax.text(
            0.008,
            level,
            f"{ratio * 100:g}% · {level:g}",
            transform=price_ax.get_yaxis_transform(),  # x — доля ширины, y — цена
            fontsize=8,
            fontweight="bold" if is_golden else "normal",
            color="darkgoldenrod" if is_golden else "dimgray",
            va="center",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.75),
        )

    fig.savefig(out_path)
    plt.close(fig)
    return out_path
