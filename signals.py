"""Зоны интереса (уровни Фибоначчи) по фьючерсам золота/серебра/меди/алюминия.

Данные — yfinance (Yahoo Finance, бесплатно, без ключа). Без TradingView
(webhook-алерты недоступны на бесплатном тарифе, а прямой сбор данных с
TradingView запрещён их пользовательским соглашением).

Важно: pandas-ta (используется в chart.py для RSI) тянет numba, который пока
не поддерживает Python 3.14 — venv проекта должен быть создан через
`python3.12 -m venv venv`, не `python3`.
"""

import logging
import os
import threading
import time

import pandas as pd
import pandas_ta  # noqa: F401 — регистрирует аксессор df.ta
import yfinance as yf

log = logging.getLogger(__name__)

# Исторически словарь называется METALS, но с добавлением нефти это просто
# "отслеживаемые инструменты" — все тикеры Yahoo Finance
METALS = {
    "Золото": "GC=F",
    "Серебро": "SI=F",
    "Медь": "HG=F",
    "Алюминий": "ALI=F",
    "Нефть Brent": "BZ=F",
}

FETCH_RETRIES = 3
FETCH_RETRY_DELAY = 2  # секунд между попытками

# Версия логики сигналов — пишется в историю алертов, чтобы при изменении
# алгоритма статистика старой и новой версий не смешивалась.
# v2: к зоне Фибоначчи добавлен поиск дивергенций RSI/цена.
ALGO_VERSION = 2

# Кэш скачанных цен по (тикер, период): дайджест на N подписчиков и алерт-цикл
# не должны ходить в Yahoo каждый раз — иначе лимиты и временные баны
_price_cache: dict[tuple[str, str, str], tuple[float, pd.DataFrame]] = {}

# yf.download не потокобезопасен: два одновременных вызова из разных задач
# смешивают ответы (в таблицу попадают оба тикера). Качаем строго по одному.
_fetch_lock = threading.Lock()


def _cache_ttl_seconds() -> float:
    # читается при каждом вызове, а не при импорте: load_dotenv в bot.py
    # срабатывает уже после импорта signals
    return float(os.getenv("CACHE_TTL_MINUTES", "10")) * 60


def fetch_prices(ticker: str, period: str = "60d", interval: str = "1d") -> pd.DataFrame:
    """Загружает OHLC с Yahoo. yfinance регулярно отдаёт пустой DataFrame или
    падает по сети — поэтому несколько попыток, а пустой ответ считается ошибкой.
    Результат кэшируется на CACHE_TTL_MINUTES минут (по инструменту и таймфрейму)."""
    key = (ticker, period, interval)
    with _fetch_lock:
        cached = _price_cache.get(key)
        if cached and time.time() - cached[0] < _cache_ttl_seconds():
            return cached[1].copy()

        last_error = None
        for attempt in range(1, FETCH_RETRIES + 1):
            try:
                df = yf.download(
                    ticker, period=period, interval=interval, progress=False, auto_adjust=True
                )
                if df is not None and not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    if df.columns.duplicated().any():
                        raise ValueError(f"смешанный ответ Yahoo для {ticker}: {list(df.columns)}")
                    _price_cache[key] = (time.time(), df)
                    return df.copy()
                last_error = ValueError(f"пустой ответ Yahoo для {ticker}")
            except Exception as e:
                last_error = e
            log.warning("fetch_prices %s: попытка %d/%d не удалась: %s", ticker, attempt, FETCH_RETRIES, last_error)
            if attempt < FETCH_RETRIES:
                time.sleep(FETCH_RETRY_DELAY)
    raise RuntimeError(f"Не удалось получить данные {ticker}: {last_error}")


# Таймфреймы для графиков: какой интервал просить у Yahoo и сколько истории.
# 4ч Yahoo не отдаёт — собирается из часовых свечей (resample).
# Алерты, дайджест и статистика всегда работают по дневному ("Д").
TIMEFRAMES = {
    "15м": {"interval": "15m", "period": "5d"},
    "30м": {"interval": "30m", "period": "10d"},
    "1ч": {"interval": "1h", "period": "10d"},
    "4ч": {"interval": "1h", "period": "30d", "resample": "4h"},
    "Д": {"interval": "1d", "period": "60d"},
    "Н": {"interval": "1wk", "period": "2y"},
}
DEFAULT_TIMEFRAME = "Д"
CHART_CANDLES = 80  # сколько последних свечей отдавать на график

TIMEFRAME_TITLES = {
    "15м": "свечи 15 минут",
    "30м": "свечи 30 минут",
    "1ч": "часовые свечи",
    "4ч": "4-часовые свечи",
    "Д": "дневные свечи",
    "Н": "недельные свечи",
}


def fetch_timeframe(ticker: str, tf: str = DEFAULT_TIMEFRAME) -> pd.DataFrame:
    """OHLC в выбранном таймфрейме, обрезанный до последних CHART_CANDLES свечей.
    Уровни Фибоначчи дальше считаются по последним 60 свечам этого таймфрейма."""
    cfg = TIMEFRAMES[tf]
    df = fetch_prices(ticker, period=cfg["period"], interval=cfg["interval"])
    if "resample" in cfg:
        df = (
            df.resample(cfg["resample"])
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna()
        )
    return df.tail(CHART_CANDLES)


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


def market_is_paused(df: pd.DataFrame, tf: str = DEFAULT_TIMEFRAME) -> bool:
    """Для внутридневных таймфреймов: свежих свечей давно не было — рынок закрыт
    (выходные или перерыв). На дневных/недельных пауза не видна и не помечается."""
    if TIMEFRAMES[tf]["interval"] in ("1d", "1wk"):
        return False
    last = df.index[-1]
    now = pd.Timestamp.now(tz=getattr(last, "tz", None))
    return (now - last) > pd.Timedelta(hours=2.5)


def close_price_after(df: pd.DataFrame, alert_day: str, horizon_days: int) -> float | None:
    """Цена закрытия первой торговой свечи спустя horizon_days после дня алерта.
    None — если такой день ещё не наступил или не попал в скачанную историю."""
    target = pd.Timestamp(alert_day) + pd.Timedelta(days=horizon_days)
    after = df.loc[df.index >= target]
    if after.empty:
        return None
    return round(float(after["Close"].iloc[0]), 2)


# --- Дивергенции RSI/цена ---
# Все пороги настраиваемые константы — «ручки», от которых зависит, что бот
# сочтёт дивергенцией. Значения ниже — общепринятая середина, не абсолют.
# Меняя их, поднимай ALGO_VERSION, чтобы старая и новая статистика не смешались.
DIVERGENCE_PIVOT_LEG = 3  # свечей с каждой стороны, чтобы признать перелом
DIVERGENCE_MIN_DISTANCE = 5  # минимум свечей между двумя переломами
DIVERGENCE_MAX_DISTANCE = 30  # максимум свечей между ними (дальше — не сравниваем)
DIVERGENCE_MIN_RSI_DIFF = 3.0  # минимальная разница RSI между переломами
DIVERGENCE_OVERSOLD = 30  # для классической бычьей — RSI должен побывать не выше этого
DIVERGENCE_OVERBOUGHT = 70  # для классической медвежьей — RSI должен побывать не ниже этого

DIVERGENCE_LABELS = {
    "classic_bullish": "Классическая бычья",
    "classic_bearish": "Классическая медвежья",
    "hidden_bullish": "Скрытая бычья",
    "hidden_bearish": "Скрытая медвежья",
}


def _find_pivots(highs: pd.Series, lows: pd.Series, leg: int) -> tuple[list[int], list[int]]:
    """Позиции локальных вершин/впадин: свеча выше (ниже) всех leg соседей
    с каждой стороны. Возвращает позиционные индексы (не даты)."""
    h, l = highs.values, lows.values
    n = len(h)
    pivot_highs, pivot_lows = [], []
    for i in range(leg, n - leg):
        if h[i] == h[i - leg : i + leg + 1].max():
            pivot_highs.append(i)
        if l[i] == l[i - leg : i + leg + 1].min():
            pivot_lows.append(i)
    return pivot_highs, pivot_lows


def find_divergences(df: pd.DataFrame) -> list[dict]:
    """Классические и скрытые дивергенции RSI/цена по двум последним переломам
    графика. Классические засчитываются только если RSI побывал в зоне
    перекупленности/перепроданности — иначе сигнал разворота ничем не подкреплён.
    Скрытые (сигнал продолжения тренда) — без этого порога."""
    d = df.copy()
    d["_rsi"] = d.ta.rsi(length=14)
    d = d.dropna(subset=["_rsi"]).reset_index(drop=True)

    min_len = DIVERGENCE_MAX_DISTANCE + 2 * DIVERGENCE_PIVOT_LEG + 1
    if len(d) < min_len:
        return []

    pivot_highs, pivot_lows = _find_pivots(d["High"], d["Low"], DIVERGENCE_PIVOT_LEG)
    divergences = []

    if len(pivot_highs) >= 2:
        i1, i2 = pivot_highs[-2], pivot_highs[-1]
        dist = i2 - i1
        price1, price2 = d["High"].iloc[i1], d["High"].iloc[i2]
        rsi1, rsi2 = d["_rsi"].iloc[i1], d["_rsi"].iloc[i2]
        if DIVERGENCE_MIN_DISTANCE <= dist <= DIVERGENCE_MAX_DISTANCE and abs(rsi2 - rsi1) >= DIVERGENCE_MIN_RSI_DIFF:
            if price2 > price1 and rsi2 < rsi1 and max(rsi1, rsi2) >= DIVERGENCE_OVERBOUGHT:
                divergences.append({
                    "type": "classic_bearish", "price1": price1, "price2": price2,
                    "rsi1": round(float(rsi1), 1), "rsi2": round(float(rsi2), 1),
                })
            elif price2 < price1 and rsi2 > rsi1:
                divergences.append({
                    "type": "hidden_bearish", "price1": price1, "price2": price2,
                    "rsi1": round(float(rsi1), 1), "rsi2": round(float(rsi2), 1),
                })

    if len(pivot_lows) >= 2:
        i1, i2 = pivot_lows[-2], pivot_lows[-1]
        dist = i2 - i1
        price1, price2 = d["Low"].iloc[i1], d["Low"].iloc[i2]
        rsi1, rsi2 = d["_rsi"].iloc[i1], d["_rsi"].iloc[i2]
        if DIVERGENCE_MIN_DISTANCE <= dist <= DIVERGENCE_MAX_DISTANCE and abs(rsi2 - rsi1) >= DIVERGENCE_MIN_RSI_DIFF:
            if price2 < price1 and rsi2 > rsi1 and min(rsi1, rsi2) <= DIVERGENCE_OVERSOLD:
                divergences.append({
                    "type": "classic_bullish", "price1": price1, "price2": price2,
                    "rsi1": round(float(rsi1), 1), "rsi2": round(float(rsi2), 1),
                })
            elif price2 > price1 and rsi2 < rsi1:
                divergences.append({
                    "type": "hidden_bullish", "price1": price1, "price2": price2,
                    "rsi1": round(float(rsi1), 1), "rsi2": round(float(rsi2), 1),
                })

    return divergences


def compute_indicators(df: pd.DataFrame) -> dict:
    """RSI(14) и ATR(14) на момент последней свечи — контекст сигнала для истории
    алертов (та же pandas-ta, что рисует RSI в chart.py)."""
    rsi = df.ta.rsi(length=14)
    atr = df.ta.atr(length=14)

    def _last(series):
        if series is None or series.empty or pd.isna(series.iloc[-1]):
            return None
        return round(float(series.iloc[-1]), 2)

    return {"rsi": _last(rsi), "atr": _last(atr)}
