"""
db/schema.py
────────────
Defines the database schema and provides a connection helper that works
with both SQLite (local) and PostgreSQL (Railway).

Run directly to initialise the database for the first time:
    python -m db.schema
"""

import sqlite3
from contextlib import contextmanager
from urllib.parse import urlparse

from config.settings import DATABASE_URL


def _is_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")


def _sqlite_path() -> str:
    # sqlite:////absolute/path  or  sqlite:///relative/path
    return DATABASE_URL.split("sqlite:///")[1]


@contextmanager
def get_connection():
    """
    Yield a database connection for either SQLite or PostgreSQL.
    Usage:
        with get_connection() as conn:
            conn.execute(...)
            conn.commit()
    """
    if _is_sqlite():
        conn = sqlite3.connect(_sqlite_path())
        conn.row_factory = sqlite3.Row   # rows accessible by column name
        try:
            yield conn
        finally:
            conn.close()
    else:
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise RuntimeError(
                "psycopg2 is required for PostgreSQL. "
                "Install it with: pip install psycopg2-binary"
            )
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
        finally:
            conn.close()


# ── DDL ───────────────────────────────────────────────────────────────────────

_CREATE_GAME_LOGS = """
CREATE TABLE IF NOT EXISTS game_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_date       TEXT    NOT NULL,
    game_id         TEXT    NOT NULL,
    fantasy_owner   TEXT    NOT NULL,
    player_id       INTEGER NOT NULL,
    player_name     TEXT    NOT NULL,
    team            TEXT,
    matchup         TEXT,
    dnp             INTEGER DEFAULT 0,
    pts             INTEGER DEFAULT 0,
    fgm             INTEGER DEFAULT 0,
    fga             INTEGER DEFAULT 0,
    fg_pct          REAL    DEFAULT 0.0,
    fg3m            INTEGER DEFAULT 0,
    fg3a            INTEGER DEFAULT 0,
    fg3_pct         REAL    DEFAULT 0.0,
    ftm             INTEGER DEFAULT 0,
    fta             INTEGER DEFAULT 0,
    ft_pct          REAL    DEFAULT 0.0,
    oreb            INTEGER DEFAULT 0,
    dreb            INTEGER DEFAULT 0,
    reb             INTEGER DEFAULT 0,
    ast             INTEGER DEFAULT 0,
    stl             INTEGER DEFAULT 0,
    blk             INTEGER DEFAULT 0,
    to_             INTEGER DEFAULT 0,
    UNIQUE (game_date, game_id, player_id)
)
"""

# PostgreSQL uses SERIAL instead of AUTOINCREMENT
_CREATE_GAME_LOGS_PG = """
CREATE TABLE IF NOT EXISTS game_logs (
    id              SERIAL  PRIMARY KEY,
    game_date       TEXT    NOT NULL,
    game_id         TEXT    NOT NULL,
    fantasy_owner   TEXT    NOT NULL,
    player_id       INTEGER NOT NULL,
    player_name     TEXT    NOT NULL,
    team            TEXT,
    matchup         TEXT,
    dnp             BOOLEAN DEFAULT FALSE,
    pts             INTEGER DEFAULT 0,
    fgm             INTEGER DEFAULT 0,
    fga             INTEGER DEFAULT 0,
    fg_pct          REAL    DEFAULT 0.0,
    fg3m            INTEGER DEFAULT 0,
    fg3a            INTEGER DEFAULT 0,
    fg3_pct         REAL    DEFAULT 0.0,
    ftm             INTEGER DEFAULT 0,
    fta             INTEGER DEFAULT 0,
    ft_pct          REAL    DEFAULT 0.0,
    oreb            INTEGER DEFAULT 0,
    dreb            INTEGER DEFAULT 0,
    reb             INTEGER DEFAULT 0,
    ast             INTEGER DEFAULT 0,
    stl             INTEGER DEFAULT 0,
    blk             INTEGER DEFAULT 0,
    to_             INTEGER DEFAULT 0,
    UNIQUE (game_date, game_id, player_id)
)
"""


_CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS standings_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT    NOT NULL,
    fantasy_owner TEXT    NOT NULL,
    place         INTEGER NOT NULL,
    total_score   REAL    NOT NULL,
    UNIQUE (snapshot_date, fantasy_owner)
)
"""

_CREATE_SNAPSHOTS_PG = """
CREATE TABLE IF NOT EXISTS standings_snapshots (
    id            SERIAL  PRIMARY KEY,
    snapshot_date TEXT    NOT NULL,
    fantasy_owner TEXT    NOT NULL,
    place         INTEGER NOT NULL,
    total_score   REAL    NOT NULL,
    UNIQUE (snapshot_date, fantasy_owner)
)
"""


def init_db():
    """Create all tables if they don't already exist."""
    ddl     = _CREATE_GAME_LOGS_PG    if not _is_sqlite() else _CREATE_GAME_LOGS
    ddl_snp = _CREATE_SNAPSHOTS_PG    if not _is_sqlite() else _CREATE_SNAPSHOTS
    with get_connection() as conn:
        conn.execute(ddl)
        conn.execute(ddl_snp)
        conn.commit()
    print("✅  Database initialised.")


def migrate_db():
    """
    Add any columns introduced after the initial schema was created.
    Safe to run multiple times — skips columns that already exist.
    Also creates new tables if they don't exist yet.
    """
    # New tables
    ddl_snp = _CREATE_SNAPSHOTS_PG if not _is_sqlite() else _CREATE_SNAPSHOTS
    with get_connection() as conn:
        conn.execute(ddl_snp)
        conn.commit()
    print("   ✓  Ensured standings_snapshots table exists.")

    # New columns on existing tables
    migrations = [
        ("dnp", "ALTER TABLE game_logs ADD COLUMN dnp INTEGER DEFAULT 0"),
    ]

    with get_connection() as conn:
        if _is_sqlite():
            rows = conn.execute("PRAGMA table_info(game_logs)").fetchall()
            existing = {row["name"] for row in rows}
        else:
            rows = conn.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'game_logs'
            """).fetchall()
            existing = {row["column_name"] for row in rows}

        for col_name, alter_sql in migrations:
            if col_name not in existing:
                conn.execute(alter_sql)
                print(f"   ✓  Added column: {col_name}")
            else:
                print(f"   –  Column already exists: {col_name}")
        conn.commit()

    print("✅  Migration complete.")


if __name__ == "__main__":
    init_db()
    migrate_db()
