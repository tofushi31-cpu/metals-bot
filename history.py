"""SQLite (metals.db): история алертов — дедупликация и накопление статистики
«сколько раз зона отработала» — плюс подписчики (оплата через Telegram Stars)."""

import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.getenv("METALS_DB", Path(__file__).parent / "metals.db"))

# Горизонты дозаписи результатов: через сколько дней после алерта фиксируем цену
OUTCOME_HORIZONS = (1, 3, 7)

# Контекст сигнала и результаты — колонки добавляются к старым базам на лету
_ALERT_EXTRA_COLUMNS = {
    "timeframe": "TEXT",  # пока всегда 'D' — бот работает на дневных свечах
    "rsi": "REAL",
    "atr": "REAL",
    "algo_version": "INTEGER",
    "price_1d": "REAL",
    "price_3d": "REAL",
    "price_7d": "REAL",
}


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
    existing = {row[1] for row in conn.execute("PRAGMA table_info(alerts)")}
    for column, col_type in _ALERT_EXTRA_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE alerts ADD COLUMN {column} {col_type}")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY,
            expires_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS gifts (
            code TEXT PRIMARY KEY,
            days INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            used_by INTEGER,
            used_at TEXT
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


def record_alert(
    metal: str,
    ratio: float,
    price: float,
    rsi: float | None = None,
    atr: float | None = None,
    algo_version: int | None = None,
    db_path=DB_PATH,
):
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT INTO alerts (metal, ratio, price, day, timeframe, rsi, atr, algo_version) "
            "VALUES (?, ?, ?, ?, 'D', ?, ?, ?)",
            (metal, ratio, price, date.today().isoformat(), rsi, atr, algo_version),
        )


def alerts_missing_outcomes(metal: str, db_path=DB_PATH) -> list[dict]:
    """Алерты этого инструмента, у которых ещё не записана цена хотя бы по
    одному горизонту (1/3/7 дней)."""
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, day, price_1d, price_3d, price_7d FROM alerts "
            "WHERE metal = ? AND (price_1d IS NULL OR price_3d IS NULL OR price_7d IS NULL)",
            (metal,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "day": r[1],
            "missing": [h for h, v in zip(OUTCOME_HORIZONS, r[2:]) if v is None],
        }
        for r in rows
    ]


def record_outcome(alert_id: int, horizon_days: int, price: float, db_path=DB_PATH):
    if horizon_days not in OUTCOME_HORIZONS:
        raise ValueError(f"неизвестный горизонт: {horizon_days}")
    with _conn(db_path) as conn:
        conn.execute(
            f"UPDATE alerts SET price_{horizon_days}d = ? WHERE id = ?",
            (price, alert_id),
        )


def level_stats(db_path=DB_PATH) -> list[dict]:
    """Сводка по инструменту+уровню: сколько сигналов и среднее движение цены
    через 1/3/7 дней (в % от цены сигнала). Для /stats."""
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT metal, ratio, COUNT(*), "
            "AVG((price_1d - price) / price * 100), "
            "AVG((price_3d - price) / price * 100), "
            "AVG((price_7d - price) / price * 100), "
            "COUNT(price_7d) "
            "FROM alerts GROUP BY metal, ratio ORDER BY metal, ratio"
        ).fetchall()
    return [
        {
            "metal": r[0],
            "ratio": r[1],
            "signals": r[2],
            "avg_1d": r[3],
            "avg_3d": r[4],
            "avg_7d": r[5],
            "with_7d": r[6],
        }
        for r in rows
    ]


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


def create_gift(days: int, db_path=DB_PATH) -> str:
    """Одноразовый подарочный код на подписку — вставляется в ссылку t.me/...?start=gift_<код>."""
    code = secrets.token_urlsafe(8)
    with _conn(db_path) as conn:
        conn.execute("INSERT INTO gifts (code, days) VALUES (?, ?)", (code, days))
    return code


def redeem_gift(code: str, user_id: int, db_path=DB_PATH) -> int | None:
    """Погашает код: возвращает число дней подписки или None, если код
    не существует или уже использован. Отметка used_by атомарная —
    два человека по одной ссылке подписку не получат."""
    with _conn(db_path) as conn:
        cur = conn.execute(
            "UPDATE gifts SET used_by = ?, used_at = datetime('now') "
            "WHERE code = ? AND used_by IS NULL",
            (user_id, code),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT days FROM gifts WHERE code = ?", (code,)).fetchone()
    return row[0]


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
