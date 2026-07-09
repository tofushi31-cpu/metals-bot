"""Зоны интереса (уровни Фибоначчи) по фьючерсам золота/серебра/меди/алюминия.

Данные — yfinance (Yahoo Finance, бесплатно, без ключа). Без TradingView
(webhook-алерты недоступны на бесплатном тарифе, а прямой сбор данных с
TradingView запрещён их пользовательским соглашением).

Важно: pandas-ta (используется в chart.py для RSI) тянет numba, который пока
не поддерживает Python 3.14 — venv проекта должен быть создан через
`python3.12 -m venv venv`, не `python3`.
"""

import logging
import time

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

METALS = {
    "Золото": "GC=F",
    "Серебро": "SI=F",
    "Медь": "HG=F",
    "Алюминий": "ALI=F",
}

FETCH_RETRIES = 3
FETCH_RETRY_DELAY = 2  # секунд между попытками


def fetch_prices(ticker: str, period: str = "60d") -> pd.DataFrame:
    """Загружает OHLC с Yahoo. yfinance регулярно отдаёт пустой DataFrame или
    падает по сети — поэтому несколько попыток, а пустой ответ считается ошибкой."""
    last_error = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df
            last_error = ValueError(f"пустой ответ Yahoo для {ticker}")
        except Exception as e:
            last_error = e
        log.warning("fetch_prices %s: попытка %d/%d не удалась: %s", ticker, attempt, FETCH_RETRIES, last_error)
        if attempt < FETCH_RETRIES:
            time.sleep(FETCH_RETRY_DELAY)
    raise RuntimeError(f"Не удалось получить данные {ticker}: {last_error}")


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
