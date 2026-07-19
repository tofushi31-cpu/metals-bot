"""Свечной график с зонами Фибоначчи и RSI — рендерится в PNG для отправки в Telegram.

Бесплатно, без TradingView: mplfinance поверх тех же данных yfinance,
что использует signals.py.
"""

import matplotlib.pyplot as plt
import pandas as pd
import pandas_ta  # noqa: F401 — регистрирует аксессор df.ta
import mplfinance as mpf

GOLDEN_RATIO = 0.618


def render_chart(df: pd.DataFrame, zones: dict, metal_name: str, out_path: str) -> str:
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
        title=f"\n{metal_name} — зоны Фибоначчи",
        hlines=dict(hlines=hline_values, colors=hline_colors, linewidths=hline_widths, linestyle="--"),
        addplot=[rsi_panel],
        panel_ratios=(3, 1),
        volume=False,
        figsize=(10, 7),
        returnfig=True,
    )

    # Подпись каждого уровня слева на самой линии: "61.8% · 4269.13"
    price_ax = axes[0]
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
