import pandas as pd

from captions import format_metal_caption, format_zone_alert
from signals import compute_fib_zones


def _zones():
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    close = [100.0 + i * 0.3 for i in range(60)]
    df = pd.DataFrame(
        {
            "Open": close,
            "High": [c + 0.5 for c in close],
            "Low": [c - 0.5 for c in close],
            "Close": close,
            "Volume": [1000] * 60,
        },
        index=dates,
    )
    return compute_fib_zones(df)


def test_caption_contains_levels_and_terminal_hint():
    caption = format_metal_caption("Золото", _zones())

    assert "Золото" in caption
    assert "61.8% (золотое сечение)" in caption
    assert "ближайший" in caption
    assert "GC1!" in caption


def test_zone_alert_mentions_metal_and_level():
    z = _zones()
    text = format_zone_alert("Медь", z)

    assert "Медь" in text
    assert str(z["current_price"]) in text
    assert "Не финансовый совет" in text
