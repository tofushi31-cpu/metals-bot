import sqlite3

import db


def test_init_db_creates_items_table(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()

    conn = sqlite3.connect(db.DB_PATH)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
    ).fetchall()
    conn.close()

    assert len(tables) == 1
