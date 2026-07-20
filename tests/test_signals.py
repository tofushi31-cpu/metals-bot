import pandas as pd

import signals
from signals import close_price_after, compute_fib_zones, compute_indicators, fetch_prices


def _fake_ohlc(n=60, start=100.0, step=0.3):
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = [start + i * step for i in range(n)]
    return pd.DataFrame(
        {
            "Open": close,
            "High": [c + 0.5 for c in close],
            "Low": [c - 0.5 for c in close],
            "Close": close,
            "Volume": [1000] * n,
        },
        index=dates,
    )


def _ohlc_from_deltas(deltas, start=100.0):
    """Свечи по последовательности приращений цены закрытия — удобно строить
    конкретный узор для проверки дивергенций."""
    closes = [start]
    for d in deltas:
        closes.append(closes[-1] + d)
    closes = closes[1:]
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 0.3 for c in closes],
            "Low": [c - 0.3 for c in closes],
            "Close": closes,
            "Volume": [1000] * len(closes),
        },
        index=dates,
    )


def test_compute_fib_zones_levels_between_low_and_high():
    df = _fake_ohlc()
    zones = compute_fib_zones(df)

    assert zones["low"] < zones["levels"][0.618] < zones["high"]
    assert zones["levels"][0.0] == zones["high"]
    assert zones["levels"][1.0] == zones["low"]


def test_compute_fib_zones_detects_near_zone_at_golden_ratio():
    df = _fake_ohlc(n=60, start=0.0, step=1.0)  # low=0, high~59.5, диапазон известен
    golden_level = df["High"].max() - (df["High"].max() - df["Low"].min()) * 0.618
    df.loc[df.index[-1], "Close"] = golden_level  # цена точно на уровне золотого сечения

    zones = compute_fib_zones(df)

    assert zones["nearest_ratio"] == 0.618
    assert zones["near_zone"] is True


def test_fetch_prices_uses_cache_within_ttl(monkeypatch):
    calls = []

    def fake_download(ticker, **kwargs):
        calls.append(ticker)
        return _fake_ohlc()

    monkeypatch.setattr(signals.yf, "download", fake_download)
    signals._price_cache.clear()

    first = fetch_prices("GC=F")
    second = fetch_prices("GC=F")

    assert len(calls) == 1  # второй вызов — из кэша, без похода в Yahoo
    pd.testing.assert_frame_equal(first, second)

    fetch_prices("SI=F")
    assert len(calls) == 2  # другой инструмент кэшируется отдельно


def test_fetch_prices_cache_expires(monkeypatch):
    calls = []

    def fake_download(ticker, **kwargs):
        calls.append(ticker)
        return _fake_ohlc()

    monkeypatch.setattr(signals.yf, "download", fake_download)
    monkeypatch.setenv("CACHE_TTL_MINUTES", "0")
    signals._price_cache.clear()

    fetch_prices("GC=F")
    fetch_prices("GC=F")

    assert len(calls) == 2  # TTL 0 — кэш сразу протухает


def test_compute_indicators_returns_rsi_and_atr():
    ind = compute_indicators(_fake_ohlc())

    assert ind["rsi"] is not None and 0 <= ind["rsi"] <= 100
    assert ind["atr"] is not None and ind["atr"] > 0


def test_fetch_timeframe_4h_resamples_hourly(monkeypatch):
    """4ч склеивается из часовых свечей: high — максимум четырёх, объём — сумма."""
    def fake_download(ticker, **kwargs):
        assert kwargs["interval"] == "1h"
        dates = pd.date_range("2026-01-01", periods=40, freq="h")
        close = [100.0 + i for i in range(40)]
        return pd.DataFrame(
            {
                "Open": close,
                "High": [c + 0.5 for c in close],
                "Low": [c - 0.5 for c in close],
                "Close": close,
                "Volume": [1000] * 40,
            },
            index=dates,
        )

    monkeypatch.setattr(signals.yf, "download", fake_download)
    signals._price_cache.clear()

    df = signals.fetch_timeframe("GC=F", "4ч")

    assert df.index[1] - df.index[0] == pd.Timedelta(hours=4)
    assert df["Volume"].iloc[0] == 4000  # четыре часовых по 1000
    assert df["High"].iloc[0] == 103.5  # максимум первых четырёх часов
    assert df["Open"].iloc[0] == 100.0 and df["Close"].iloc[0] == 103.0


def test_fetch_timeframe_trims_to_chart_candles(monkeypatch):
    def fake_download(ticker, **kwargs):
        assert kwargs["interval"] == "15m"
        dates = pd.date_range("2026-01-01", periods=300, freq="15min")
        close = [100.0] * 300
        return pd.DataFrame(
            {"Open": close, "High": close, "Low": close, "Close": close, "Volume": [1] * 300},
            index=dates,
        )

    monkeypatch.setattr(signals.yf, "download", fake_download)
    signals._price_cache.clear()

    df = signals.fetch_timeframe("GC=F", "15м")

    assert len(df) == signals.TIMEFRAMES["15м"]["candles"]


def test_market_is_paused():
    hours_ago = pd.Timestamp.now() - pd.Timedelta(hours=30)
    stale = pd.DataFrame({"Close": [1.0]}, index=[hours_ago])
    fresh = pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp.now()])

    assert signals.market_is_paused(stale, "15м") is True
    assert signals.market_is_paused(fresh, "15м") is False
    # на дневных/недельных пауза не помечается, даже если свеча старая
    assert signals.market_is_paused(stale, "Д") is False
    assert signals.market_is_paused(stale, "Н") is False


def test_no_divergence_on_monotonic_trend():
    # монотонный рост без переломов — пивотов нет, дивергенций тоже
    assert signals.find_divergences(_fake_ohlc(n=60)) == []


def test_classic_bullish_divergence():
    # резкий обвал (RSI около 0) -> отскок -> пологое снижение к более низкому
    # минимуму цены, но с более высоким RSI (перепроданность слабее)
    deltas = [-3] * 10 + [2] * 5 + [-2, 0.5] * 10 + [1] * 6
    divs = signals.find_divergences(_ohlc_from_deltas(deltas))

    found = [d for d in divs if d["type"] == "classic_bullish"]
    assert len(found) == 1
    assert found[0]["price2"] < found[0]["price1"]  # цена: ниже минимум
    assert found[0]["rsi2"] > found[0]["rsi1"]  # RSI: выше минимум
    assert found[0]["rsi1"] <= signals.DIVERGENCE_OVERSOLD  # была перепроданность


def test_classic_bearish_divergence():
    # резкое ралли (RSI около 100) -> откат -> пологий рост к более высокому
    # максимуму цены, но с более слабым RSI (перекупленность слабее)
    deltas = [3] * 10 + [-2] * 5 + [2, -0.5] * 10 + [-1] * 6
    divs = signals.find_divergences(_ohlc_from_deltas(deltas))

    found = [d for d in divs if d["type"] == "classic_bearish"]
    assert len(found) == 1
    assert found[0]["price2"] > found[0]["price1"]  # цена: выше максимум
    assert found[0]["rsi2"] < found[0]["rsi1"]  # RSI: ниже максимум
    assert found[0]["rsi1"] >= signals.DIVERGENCE_OVERBOUGHT  # была перекупленность


def test_hidden_bullish_divergence():
    # восходящий тренд: сначала пологая коррекция (RSI остаётся высоким),
    # затем более глубокая, но цена делает более высокий минимум — продолжение роста
    deltas = [3] * 8 + [-1] * 3 + [3] * 8 + [-2, -0.3] * 6 + [1] * 10
    divs = signals.find_divergences(_ohlc_from_deltas(deltas))

    found = [d for d in divs if d["type"] == "hidden_bullish"]
    assert len(found) == 1
    assert found[0]["price2"] > found[0]["price1"]  # цена: выше минимум
    assert found[0]["rsi2"] < found[0]["rsi1"]  # RSI: ниже минимум


def test_hidden_bearish_divergence():
    # нисходящий тренд: сначала пологий отскок (RSI остаётся низким), затем
    # более сильный, но цена делает более низкий максимум — продолжение падения
    deltas = [-3] * 8 + [1] * 3 + [-3] * 8 + [2, 0.3] * 6 + [-1] * 10
    divs = signals.find_divergences(_ohlc_from_deltas(deltas))

    found = [d for d in divs if d["type"] == "hidden_bearish"]
    assert len(found) == 1
    assert found[0]["price2"] < found[0]["price1"]  # цена: ниже максимум
    assert found[0]["rsi2"] > found[0]["rsi1"]  # RSI: выше максимум


def test_daily_data_is_stale():
    yesterday = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    today = pd.Timestamp.now()

    stale = pd.DataFrame({"Close": [1.0]}, index=[yesterday])
    fresh = pd.DataFrame({"Close": [1.0]}, index=[today])

    assert signals.daily_data_is_stale(stale) is True
    assert signals.daily_data_is_stale(fresh) is False


def test_close_price_after():
    df = _fake_ohlc()  # свечи с 2026-01-01, шаг 0.3 в день от 100.0

    assert close_price_after(df, "2026-01-01", 3) == round(100.0 + 3 * 0.3, 2)
    # горизонт за пределами истории — результата ещё нет
    assert close_price_after(df, "2026-02-25", 7) is None
