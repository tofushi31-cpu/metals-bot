"""SQLite-хранилище собранных постов/статей."""

import sqlite3

DB_PATH = "radar.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,      -- 'rss' | 'telegram'
            source_name TEXT NOT NULL,
            title TEXT,
            text TEXT NOT NULL,
            url TEXT,
            published_at TEXT,
            collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_name, url)
        )
    """)
    conn.commit()
    conn.close()
