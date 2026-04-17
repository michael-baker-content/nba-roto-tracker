"""
tests/conftest.py
─────────────────
Shared pytest fixtures. All tests run against a temporary in-memory
SQLite database — no real database file or NBA API calls required.
"""

import sqlite3
import pytest


@pytest.fixture
def db_conn():
    """
    Yield a fresh in-memory SQLite connection with the full schema applied.
    Each test gets its own isolated database.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE game_logs (
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
        );

        CREATE TABLE standings_snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT    NOT NULL,
            fantasy_owner TEXT    NOT NULL,
            place         INTEGER NOT NULL,
            total_score   REAL    NOT NULL,
            UNIQUE (snapshot_date, fantasy_owner)
        );
    """)

    yield conn
    conn.close()
