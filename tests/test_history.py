import sqlite3
from datetime import date, timedelta

from history import (
    alerts_missing_outcomes,
    create_gift,
    level_stats,
    record_alert,
    record_outcome,
    redeem_gift,
    was_alerted_today,
)


def test_alert_dedup_per_day(tmp_path):
    db = tmp_path / "test.db"

    assert was_alerted_today("Золото", 0.618, db_path=db) is False

    record_alert("Золото", 0.618, 2400.5, db_path=db)

    assert was_alerted_today("Золото", 0.618, db_path=db) is True
    assert was_alerted_today("Золото", 0.5, db_path=db) is False
    assert was_alerted_today("Серебро", 0.618, db_path=db) is False


def test_record_alert_saves_context(tmp_path):
    db = tmp_path / "test.db"

    record_alert("Золото", 0.618, 2400.5, rsi=34.2, atr=18.7, algo_version=1, db_path=db)

    row = sqlite3.connect(db).execute(
        "SELECT timeframe, rsi, atr, algo_version FROM alerts"
    ).fetchone()
    assert row == ("D", 34.2, 18.7, 1)


def test_outcomes_fill_and_stats(tmp_path):
    db = tmp_path / "test.db"
    record_alert("Золото", 0.618, 2000.0, db_path=db)
    # алерт "трёхдневной давности": день двигаем вручную, как будто время прошло
    old_day = (date.today() - timedelta(days=3)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE alerts SET day = ?", (old_day,))

    pending = alerts_missing_outcomes("Золото", db_path=db)
    assert len(pending) == 1
    assert pending[0]["missing"] == [1, 3, 7]

    record_outcome(pending[0]["id"], 1, 2020.0, db_path=db)  # +1% за день
    record_outcome(pending[0]["id"], 3, 2040.0, db_path=db)  # +2% за 3 дня

    pending = alerts_missing_outcomes("Золото", db_path=db)
    assert pending[0]["missing"] == [7]
    assert alerts_missing_outcomes("Серебро", db_path=db) == []

    stats = level_stats(db_path=db)
    assert len(stats) == 1
    assert stats[0]["metal"] == "Золото"
    assert stats[0]["signals"] == 1
    assert round(stats[0]["avg_1d"], 2) == 1.0
    assert round(stats[0]["avg_3d"], 2) == 2.0
    assert stats[0]["avg_7d"] is None


def test_gift_code_is_single_use(tmp_path):
    db = tmp_path / "test.db"
    code = create_gift(30, db_path=db)

    assert redeem_gift(code, user_id=111, db_path=db) == 30  # первый получает
    assert redeem_gift(code, user_id=222, db_path=db) is None  # второй — нет
    assert redeem_gift("несуществующий", user_id=333, db_path=db) is None


def test_old_db_gets_new_columns(tmp_path):
    """База, созданная до появления контекста, должна обновиться без ошибок."""
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metal TEXT NOT NULL,
                ratio REAL NOT NULL,
                price REAL NOT NULL,
                day TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )"""
        )
        conn.execute(
            "INSERT INTO alerts (metal, ratio, price, day) VALUES ('Золото', 0.5, 2000.0, '2026-07-01')"
        )

    record_alert("Золото", 0.618, 2400.5, rsi=50.0, db_path=db)

    pending = alerts_missing_outcomes("Золото", db_path=db)
    assert len(pending) == 2  # старый и новый алерты видны, база не сломалась
