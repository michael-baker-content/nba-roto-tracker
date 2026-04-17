"""
db/store.py
───────────
Writes a game-log DataFrame (produced by nba.boxscore.build_game_logs)
into the game_logs table. Uses upsert semantics so re-running the pipeline
for the same date is always safe — existing rows are updated, not duplicated.
"""

from datetime import date

import pandas as pd

from db.schema import get_connection, init_db


# DataFrame column → database column
_COL_MAP = {
    "Fantasy_Owner": "fantasy_owner",
    "PLAYER_ID":     "player_id",
    "PLAYER":        "player_name",
    "TEAM":          "team",
    "MATCHUP":       "matchup",
    "DNP":           "dnp",
    "PTS":           "pts",
    "FGM":           "fgm",
    "FGA":           "fga",
    "FG_PCT":        "fg_pct",
    "FG3M":          "fg3m",
    "FG3A":          "fg3a",
    "FG3_PCT":       "fg3_pct",
    "FTM":           "ftm",
    "FTA":           "fta",
    "FT_PCT":        "ft_pct",
    "OREB":          "oreb",
    "DREB":          "dreb",
    "REB":           "reb",
    "AST":           "ast",
    "STL":           "stl",
    "BLK":           "blk",
    "TO":            "to_",
}

_SQLITE_UPSERT = """
INSERT INTO game_logs
    (game_date, game_id, fantasy_owner, player_id, player_name, team, matchup, dnp,
     pts, fgm, fga, fg_pct, fg3m, fg3a, fg3_pct,
     ftm, fta, ft_pct, oreb, dreb, reb, ast, stl, blk, to_)
VALUES
    (:game_date, :game_id, :fantasy_owner, :player_id, :player_name, :team, :matchup, :dnp,
     :pts, :fgm, :fga, :fg_pct, :fg3m, :fg3a, :fg3_pct,
     :ftm, :fta, :ft_pct, :oreb, :dreb, :reb, :ast, :stl, :blk, :to_)
ON CONFLICT (game_date, game_id, player_id) DO UPDATE SET
    fantasy_owner = excluded.fantasy_owner,
    player_name   = excluded.player_name,
    team          = excluded.team,
    matchup       = excluded.matchup,
    dnp           = excluded.dnp,
    pts  = excluded.pts,  fgm  = excluded.fgm,  fga  = excluded.fga,
    fg_pct = excluded.fg_pct,
    fg3m = excluded.fg3m, fg3a = excluded.fg3a, fg3_pct = excluded.fg3_pct,
    ftm  = excluded.ftm,  fta  = excluded.fta,  ft_pct = excluded.ft_pct,
    oreb = excluded.oreb, dreb = excluded.dreb, reb  = excluded.reb,
    ast  = excluded.ast,  stl  = excluded.stl,  blk  = excluded.blk,
    to_  = excluded.to_
"""

_PG_UPSERT = """
INSERT INTO game_logs
    (game_date, game_id, fantasy_owner, player_id, player_name, team, matchup, dnp,
     pts, fgm, fga, fg_pct, fg3m, fg3a, fg3_pct,
     ftm, fta, ft_pct, oreb, dreb, reb, ast, stl, blk, to_)
VALUES
    (%(game_date)s, %(game_id)s, %(fantasy_owner)s, %(player_id)s, %(player_name)s,
     %(team)s, %(matchup)s, %(dnp)s,
     %(pts)s, %(fgm)s, %(fga)s, %(fg_pct)s, %(fg3m)s, %(fg3a)s, %(fg3_pct)s,
     %(ftm)s, %(fta)s, %(ft_pct)s, %(oreb)s, %(dreb)s, %(reb)s,
     %(ast)s, %(stl)s, %(blk)s, %(to_)s)
ON CONFLICT (game_date, game_id, player_id) DO UPDATE SET
    fantasy_owner = EXCLUDED.fantasy_owner,
    player_name   = EXCLUDED.player_name,
    team          = EXCLUDED.team,
    matchup       = EXCLUDED.matchup,
    dnp           = EXCLUDED.dnp,
    pts  = EXCLUDED.pts,  fgm  = EXCLUDED.fgm,  fga  = EXCLUDED.fga,
    fg_pct = EXCLUDED.fg_pct,
    fg3m = EXCLUDED.fg3m, fg3a = EXCLUDED.fg3a, fg3_pct = EXCLUDED.fg3_pct,
    ftm  = EXCLUDED.ftm,  fta  = EXCLUDED.fta,  ft_pct = EXCLUDED.ft_pct,
    oreb = EXCLUDED.oreb, dreb = EXCLUDED.dreb, reb  = EXCLUDED.reb,
    ast  = EXCLUDED.ast,  stl  = EXCLUDED.stl,  blk  = EXCLUDED.blk,
    to_  = EXCLUDED.to_
"""


def _is_sqlite() -> bool:
    from config.settings import DATABASE_URL
    return DATABASE_URL.startswith("sqlite")


def save_game_logs(df: pd.DataFrame, game_date: date, game_id: str):
    """
    Upsert all rows in df for a single game into game_logs.

    Parameters
    ----------
    df        : DataFrame returned by build_game_logs(), filtered to one game
    game_date : the date of the game
    game_id   : NBA game ID string (e.g. "0042500401")
    """
    init_db()   # no-op if tables already exist

    rows = []
    for _, row in df.iterrows():
        record = {db_col: row.get(df_col) for df_col, db_col in _COL_MAP.items()}
        record["game_date"] = str(game_date)
        record["game_id"]   = game_id
        # Ensure percentage values are plain Python floats
        for pct in ("fg_pct", "fg3_pct", "ft_pct"):
            if record[pct] is not None:
                record[pct] = float(record[pct])
        # Ensure dnp is stored as int (SQLite has no native boolean)
        record["dnp"] = int(bool(record.get("dnp", False)))
        rows.append(record)

    if not rows:
        return

    sql = _SQLITE_UPSERT if _is_sqlite() else _PG_UPSERT

    with get_connection() as conn:
        if _is_sqlite():
            conn.executemany(sql, rows)
        else:
            cursor = conn.cursor()
            cursor.executemany(sql, rows)
        conn.commit()

    print(f"   💾  Saved {len(rows)} row(s) to database for game {game_id}.")


_SQLITE_SNAPSHOT = """
INSERT INTO standings_snapshots (snapshot_date, fantasy_owner, place, total_score)
VALUES (:snapshot_date, :fantasy_owner, :place, :total_score)
ON CONFLICT (snapshot_date, fantasy_owner) DO UPDATE SET
    place       = excluded.place,
    total_score = excluded.total_score
"""

_PG_SNAPSHOT = """
INSERT INTO standings_snapshots (snapshot_date, fantasy_owner, place, total_score)
VALUES (%(snapshot_date)s, %(fantasy_owner)s, %(place)s, %(total_score)s)
ON CONFLICT (snapshot_date, fantasy_owner) DO UPDATE SET
    place       = EXCLUDED.place,
    total_score = EXCLUDED.total_score
"""


def save_standings_snapshot(standings: list[dict], snapshot_date: "date"):
    """
    Persist the current standings as a snapshot for snapshot_date.
    Called from main.py after game logs are saved so the snapshot
    reflects the standings after that day's games.
    """
    rows = [
        {
            "snapshot_date": str(snapshot_date),
            "fantasy_owner": row["fantasy_owner"],
            "place":         row["place"],
            "total_score":   float(row["total_score"]),
        }
        for row in standings
    ]

    if not rows:
        return

    sql = _SQLITE_SNAPSHOT if _is_sqlite() else _PG_SNAPSHOT

    with get_connection() as conn:
        if _is_sqlite():
            conn.executemany(sql, rows)
        else:
            cursor = conn.cursor()
            cursor.executemany(sql, rows)
        conn.commit()

    print(f"   📸  Saved standings snapshot for {snapshot_date}.")
