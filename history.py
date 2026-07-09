"""SQLite (metals.db): история алертов — дедупликация и накопление статистики
«сколько раз зона отработала» — плюс подписчики (оплата через Telegram Stars)."""

import os
import sqlite3
from datetime import date, datetime, timedelta
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
    conn.execute(
        """CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY,
            expires_at TEXT NOT NULL
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


def add_subscription(user_id: int, days: int, db_path=DB_PATH) -> str:
    """Продлевает подписку от текущего момента или от конца действующей."""
    now = datetime.now()
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT expires_at FROM subscribers WHERE user_id = ?", (user_id,)
        ).fetchone()
        base = now
        if row:
            current = datetime.fromisoformat(row[0])
            if current > now:
                base = current
        expires = (base + timedelta(days=days)).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO subscribers (user_id, expires_at) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET expires_at = excluded.expires_at",
            (user_id, expires),
        )
    return expires


def is_subscriber(user_id: int, db_path=DB_PATH) -> bool:
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM subscribers WHERE user_id = ? AND expires_at > ?",
            (user_id, datetime.now().isoformat(timespec="seconds")),
        ).fetchone()
    return row is not None


def active_subscribers(db_path=DB_PATH) -> list[int]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id FROM subscribers WHERE expires_at > ?",
            (datetime.now().isoformat(timespec="seconds"),),
        ).fetchall()
    return [r[0] for r in rows]
