import pandas as pd

from chart import render_chart
from signals import compute_fib_zones


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


def test_render_chart_creates_png(tmp_path):
    df = _fake_ohlc()
    zones = compute_fib_zones(df)
    out = tmp_path / "chart.png"

    result = render_chart(df, zones, "Тест", str(out))

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 5000  # не пустой файл, а реальная картинка


def test_render_chart_with_divergence(tmp_path):
    df = _fake_ohlc()
    zones = compute_fib_zones(df)
    out = tmp_path / "chart_div.png"
    divergences = [{
        "type": "classic_bullish",
        "price1": df["Low"].iloc[10], "price2": df["Low"].iloc[20],
        "rsi1": 25.0, "rsi2": 35.0,
        "date1": df.index[10], "date2": df.index[20],
    }]

    render_chart(df, zones, "Тест", str(out), divergences=divergences)

    assert out.exists()
    assert out.stat().st_size > 5000
