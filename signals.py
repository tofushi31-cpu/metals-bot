"""Технические сигналы по фьючерсам золота/серебра/меди/алюминия.

Данные — yfinance (Yahoo Finance, бесплатно, без ключа). Индикаторы — pandas-ta,
локально, без LLM и без TradingView (webhook-алерты TradingView недоступны на
бесплатном тарифе, а прямой сбор данных с TradingView запрещён их пользовательским
соглашением — см. tmp/plans/radar-potrebnostey.md).

Важно: pandas-ta тянет numba, который пока не поддерживает Python 3.14 — venv
проекта должен быть создан через `python3.12 -m venv venv`, не `python3`.

Это только индикаторы (RSI, MACD, пересечение скользящих) — не "паттерны на графике"
в смысле фигур типа треугольник/голова-плечи. Такие фигуры плохо формализуются
и распознаются алгоритмически ненадёжно даже у профессионалов — сознательно не
берёмся их автоматизировать на этом этапе.
"""

import pandas as pd
import pandas_ta as ta
import yfinance as yf

METALS = {
    "Золото": "GC=F",
    "Серебро": "SI=F",
    "Медь": "HG=F",
    "Алюминий": "ALI=F",
}


def fetch_prices(ticker: str, period: str = "60d") -> pd.DataFrame:
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def compute_signal(df: pd.DataFrame) -> dict:
    """Считает RSI(14) и MACD, возвращает последние значения и простую интерпретацию."""
    df = df.copy()
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)

    rsi = df["RSI_14"].iloc[-1]
    macd = df["MACD_12_26_9"].iloc[-1]
    macd_signal = df["MACDs_12_26_9"].iloc[-1]

    if rsi >= 70:
        rsi_note = "перекуплен"
    elif rsi <= 30:
        rsi_note = "перепродан"
    else:
        rsi_note = "нейтрально"

    macd_note = "бычье пересечение" if macd > macd_signal else "медвежье пересечение"

    return {
        "rsi": round(float(rsi), 2),
        "rsi_note": rsi_note,
        "macd": round(float(macd), 3),
        "macd_signal": round(float(macd_signal), 3),
        "macd_note": macd_note,
    }


def check_all_metals() -> dict[str, dict]:
    results = {}
    for name, ticker in METALS.items():
        df = fetch_prices(ticker)
        results[name] = compute_signal(df)
    return results


FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
FIB_LABELS = {
    0.0: "0%",
    0.236: "23.6%",
    0.382: "38.2%",
    0.5: "50%",
    0.618: "61.8% (золотое сечение)",
    0.786: "78.6%",
    1.0: "100%",
}
NEAR_ZONE_PCT = 1.0  # в пределах какого % от уровня считаем "зоной интереса"


def compute_fib_zones(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Уровни коррекции Фибоначчи по последнему свингу high/low — зоны интереса
    для входа/выхода. Не паттерн в смысле фигуры, а разметка уровней цены."""
    window = df.tail(lookback)
    high = float(window["High"].max())
    low = float(window["Low"].min())
    diff = high - low
    current_price = float(df["Close"].iloc[-1])

    levels = {ratio: round(high - diff * ratio, 2) for ratio in FIB_RATIOS}

    nearest_ratio = min(levels, key=lambda r: abs(levels[r] - current_price))
    nearest_level = levels[nearest_ratio]
    distance_pct = abs(current_price - nearest_level) / current_price * 100

    return {
        "high": round(high, 2),
        "low": round(low, 2),
        "current_price": round(current_price, 2),
        "levels": levels,
        "nearest_ratio": nearest_ratio,
        "nearest_level": nearest_level,
        "near_zone": distance_pct <= NEAR_ZONE_PCT,
    }


def check_all_fib_zones() -> dict[str, dict]:
    results = {}
    for name, ticker in METALS.items():
        df = fetch_prices(ticker)
        results[name] = compute_fib_zones(df)
    return results
