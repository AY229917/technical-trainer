"""ローカルの日足と順位。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from config import DB_PATH, DATA

DAY_MS = 86_400_000


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS candles (
                coin TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (coin, open_time)
            );
            CREATE TABLE IF NOT EXISTS rankings (
                recorded_at TEXT NOT NULL,
                coin TEXT NOT NULL,
                rank INTEGER NOT NULL,
                volume_24h REAL NOT NULL,
                PRIMARY KEY (recorded_at, coin)
            );
            CREATE TABLE IF NOT EXISTS seen (
                coin TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL
            );
            """
        )


def latest_recorded_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(recorded_at) AS t FROM rankings").fetchone()
    return row["t"] if row and row["t"] else None


def saved_coins(conn: sqlite3.Connection) -> list[str]:
    return [r["coin"] for r in conn.execute("SELECT coin FROM seen ORDER BY coin")]


def last_open_time(conn: sqlite3.Connection, coin: str) -> int | None:
    row = conn.execute(
        "SELECT MAX(open_time) AS t FROM candles WHERE coin = ?", (coin,)
    ).fetchone()
    return int(row["t"]) if row and row["t"] is not None else None


def upsert_candles(conn: sqlite3.Connection, coin: str, rows: list[dict]) -> int:
    clean = []
    for row in rows:
        if row["high"] < row["low"]:
            continue
        clean.append(row)
    conn.executemany(
        """
        INSERT INTO candles (coin, open_time, open, high, low, close, volume)
        VALUES (:coin, :open_time, :open, :high, :low, :close, :volume)
        ON CONFLICT(coin, open_time) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume
        """,
        [{**row, "coin": coin} for row in clean],
    )
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO seen (coin, first_seen) VALUES (?, ?) ON CONFLICT(coin) DO NOTHING",
        (coin, now),
    )
    return len(clean)


def insert_ranking(conn: sqlite3.Connection, recorded_at: str, rows: list[tuple[str, int, float]]) -> None:
    conn.executemany(
        "INSERT INTO rankings (recorded_at, coin, rank, volume_24h) VALUES (?, ?, ?, ?)",
        [(recorded_at, coin, rank, volume) for coin, rank, volume in rows],
    )


def load_candles(conn: sqlite3.Connection, coin: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT open_time, open, high, low, close, volume
        FROM candles WHERE coin = ? ORDER BY open_time
        """,
        (coin,),
    ).fetchall()
    return [dict(row) for row in rows]


def latest_ranking(conn: sqlite3.Connection, limit: int) -> tuple[str | None, list[dict]]:
    recorded = latest_recorded_at(conn)
    if not recorded:
        return None, []
    rows = conn.execute(
        """
        SELECT coin, rank, volume_24h
        FROM rankings
        WHERE recorded_at = ?
        ORDER BY rank
        LIMIT ?
        """,
        (recorded, limit),
    ).fetchall()
    return recorded, [dict(row) for row in rows]
