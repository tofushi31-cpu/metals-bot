import pandas as pd

from signals import compute_fib_zones, compute_signal


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


def test_compute_signal_uptrend_gives_bullish_macd():
    df = _fake_ohlc()
    signal = compute_signal(df)

    assert "rsi" in signal
    assert signal["rsi_note"] in {"перекуплен", "перепродан", "нейтрально"}
    assert signal["macd_note"] == "бычье пересечение"


def test_compute_signal_overbought_rsi_on_strong_uptrend():
    df = _fake_ohlc(step=2.0)
    signal = compute_signal(df)

    assert signal["rsi"] >= 70
    assert signal["rsi_note"] == "перекуплен"


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
