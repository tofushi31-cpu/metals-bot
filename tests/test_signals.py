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


def test_close_price_after():
    df = _fake_ohlc()  # свечи с 2026-01-01, шаг 0.3 в день от 100.0

    assert close_price_after(df, "2026-01-01", 3) == round(100.0 + 3 * 0.3, 2)
    # горизонт за пределами истории — результата ещё нет
    assert close_price_after(df, "2026-02-25", 7) is None
