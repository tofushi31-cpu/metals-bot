from history import record_alert, was_alerted_today


def test_alert_dedup_per_day(tmp_path):
    db = tmp_path / "test.db"

    assert was_alerted_today("Золото", 0.618, db_path=db) is False

    record_alert("Золото", 0.618, 2400.5, db_path=db)

    assert was_alerted_today("Золото", 0.618, db_path=db) is True
    assert was_alerted_today("Золото", 0.5, db_path=db) is False
    assert was_alerted_today("Серебро", 0.618, db_path=db) is False
