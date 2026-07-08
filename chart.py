"""Свечной график с зонами Фибоначчи и RSI — рендерится в PNG для отправки в Telegram.

Бесплатно, без TradingView: mplfinance поверх тех же данных yfinance/pandas-ta,
что использует signals.py.
"""

import pandas as pd
import mplfinance as mpf

from signals import FIB_LABELS, compute_fib_zones, fetch_prices

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

    mpf.plot(
        df,
        type="candle",
        style="charles",
        title=f"\n{metal_name} — зоны Фибоначчи",
        hlines=dict(hlines=hline_values, colors=hline_colors, linewidths=hline_widths, linestyle="--"),
        addplot=[rsi_panel],
        panel_ratios=(3, 1),
        volume=False,
        figsize=(10, 7),
        savefig=out_path,
    )
    return out_path


def render_metal_chart(metal_name: str, ticker: str, out_path: str) -> str:
    df = fetch_prices(ticker)
    zones = compute_fib_zones(df)
    return render_chart(df, zones, metal_name, out_path)
