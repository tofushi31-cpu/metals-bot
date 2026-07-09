"""История алертов в SQLite: дедупликация (один алерт по металлу+уровню в день)
и накопление статистики «сколько раз зона отработала» на будущее."""

import os
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(os.getenv("METALS_DB", Path(__file__).parent / "metals.db"))


def _conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metal TEXT NOT NULL,
            ratio REAL NOT NULL,
            price REAL NOT NULL,
            day TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    return conn


def was_alerted_today(metal: str, ratio: float, db_path=DB_PATH) -> bool:
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM alerts WHERE metal = ? AND ratio = ? AND day = ? LIMIT 1",
            (metal, ratio, date.today().isoformat()),
        ).fetchone()
    return row is not None


def record_alert(metal: str, ratio: float, price: float, db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT INTO alerts (metal, ratio, price, day) VALUES (?, ?, ?, ?)",
            (metal, ratio, price, date.today().isoformat()),
        )
