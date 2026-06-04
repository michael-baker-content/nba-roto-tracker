import psycopg2
import sqlite3

PG_URL = "postgresql://postgres:VJYsxOEjGTwPsysWcqzwjXKtpTotRgUb@monorail.proxy.rlwy.net:14517/railway"
SQLITE_PATH = "fantasy_export.db"

pg = psycopg2.connect(PG_URL)
pg_cur = pg.cursor()

sq = sqlite3.connect(SQLITE_PATH)
sq.execute("""
    CREATE TABLE IF NOT EXISTS game_logs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date     TEXT,
        game_id       TEXT,
        fantasy_owner TEXT,
        player_id     INTEGER,
        player_name   TEXT,
        team          TEXT,
        matchup       TEXT,
        dnp           INTEGER DEFAULT 0,
        pts           INTEGER DEFAULT 0,
        fgm           INTEGER DEFAULT 0,
        fga           INTEGER DEFAULT 0,
        fg_pct        REAL    DEFAULT 0.0,
        fg3m          INTEGER DEFAULT 0,
        fg3a          INTEGER DEFAULT 0,
        fg3_pct       REAL    DEFAULT 0.0,
        ftm           INTEGER DEFAULT 0,
        fta           INTEGER DEFAULT 0,
        ft_pct        REAL    DEFAULT 0.0,
        oreb          INTEGER DEFAULT 0,
        dreb          INTEGER DEFAULT 0,
        reb           INTEGER DEFAULT 0,
        ast           INTEGER DEFAULT 0,
        stl           INTEGER DEFAULT 0,
        blk           INTEGER DEFAULT 0,
        to_           INTEGER DEFAULT 0,
        UNIQUE (game_date, game_id, player_id)
    )
""")
sq.execute("""
    CREATE TABLE IF NOT EXISTS standings_snapshots (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date TEXT,
        fantasy_owner TEXT,
        place         INTEGER,
        total_score   REAL,
        UNIQUE (snapshot_date, fantasy_owner)
    )
""")
sq.commit()

for table in ("game_logs", "standings_snapshots"):
    pg_cur.execute(f"SELECT * FROM {table}")
    rows = pg_cur.fetchall()
    cols = [d[0] for d in pg_cur.description]
    cols_no_id = [c for c in cols if c != "id"]
    placeholders = ", ".join("?" * len(cols_no_id))
    col_idx = [cols.index(c) for c in cols_no_id]
    sq.executemany(
        f"INSERT OR IGNORE INTO {table} ({', '.join(cols_no_id)}) VALUES ({placeholders})",
        [[row[i] for i in col_idx] for row in rows]
    )
    print(f"Copied {len(rows)} rows from {table}")

sq.commit()
sq.close()
pg.close()
print(f"Done — saved to {SQLITE_PATH}")