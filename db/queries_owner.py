"""
db/queries_owner.py
───────────────────
Per-owner queries: season cumulative player totals and game-by-game logs.
Used by the owner team page (/owner/<name>).
"""

from db.schema import get_connection


_OWNER_GAME_LOGS_SQL = """
SELECT
    game_date,
    player_name,
    team,
    matchup,
    dnp,
    pts,
    fgm, fga,
    CASE WHEN fga > 0 THEN CAST(fgm AS REAL) / fga ELSE 0 END AS fg_pct,
    fg3m, fg3a,
    CASE WHEN fg3a > 0 THEN CAST(fg3m AS REAL) / fg3a ELSE 0 END AS fg3_pct,
    ftm, fta,
    CASE WHEN fta > 0 THEN CAST(ftm AS REAL) / fta ELSE 0 END AS ft_pct,
    oreb, dreb, reb,
    ast, stl, blk, to_
FROM game_logs
WHERE fantasy_owner = :owner
  AND game_date BETWEEN :start AND :end
ORDER BY game_date DESC, player_name ASC
"""
# Note: dnp rows ARE included here so the owner page can show a complete
# game-by-game record. The web template renders DNP rows with a badge
# instead of stats. Contrast with _OWNER_PLAYER_TOTALS_SQL which excludes dnp.

_OWNER_PLAYER_TOTALS_SQL = """
SELECT
    player_name,
    MAX(team)     AS team,
    COUNT(*)      AS games_played,
    SUM(pts)      AS pts,
    SUM(fgm)      AS fgm,
    SUM(fga)      AS fga,
    CASE WHEN SUM(fga)  > 0 THEN CAST(SUM(fgm)  AS REAL) / SUM(fga)  ELSE 0 END AS fg_pct,
    SUM(fg3m)     AS fg3m,
    SUM(fg3a)     AS fg3a,
    CASE WHEN SUM(fg3a) > 0 THEN CAST(SUM(fg3m) AS REAL) / SUM(fg3a) ELSE 0 END AS fg3_pct,
    SUM(ftm)      AS ftm,
    SUM(fta)      AS fta,
    CASE WHEN SUM(fta)  > 0 THEN CAST(SUM(ftm)  AS REAL) / SUM(fta)  ELSE 0 END AS ft_pct,
    SUM(oreb)     AS oreb,
    SUM(dreb)     AS dreb,
    SUM(reb)      AS reb,
    SUM(ast)      AS ast,
    SUM(stl)      AS stl,
    SUM(blk)      AS blk,
    SUM(to_)      AS to_
FROM game_logs
WHERE fantasy_owner = :owner
  AND game_date BETWEEN :start AND :end
  AND dnp = FALSE
GROUP BY player_name
"""
# MAX(team) aggregates the team abbreviation. Players don't change teams
# during the playoffs so MAX() always returns their actual team.
# dnp=FALSE ensures DNP rows don't count toward games_played or stat totals.


def get_owner_game_logs(owner: str, start: str, end: str) -> list[dict]:
    """
    Return every game log row for a given owner, most recent first.
    Includes DNP rows (flagged with dnp=True) for a complete game record.
    """
    with get_connection() as conn:
        rows = conn.execute(
            _OWNER_GAME_LOGS_SQL, {"owner": owner, "start": start, "end": end}
        ).fetchall()
    return [dict(r) for r in rows]


def get_owner_player_totals(owner: str, start: str, end: str) -> list[dict]:
    """
    Return season cumulative stats per player for the given owner.

    Players with no games played are included with zero stats so the
    owner page shows a complete roster even early in the season.
    DNP rows are excluded from all aggregates.
    Sorted by last name then first name.
    """
    from config.roster import ROSTER
    owner_players = [p["PLAYER"] for p in ROSTER if p["Fantasy_Owner"] == owner]

    with get_connection() as conn:
        rows = conn.execute(
            _OWNER_PLAYER_TOTALS_SQL, {"owner": owner, "start": start, "end": end}
        ).fetchall()

    db_results = {row["player_name"]: dict(row) for row in rows}
    result = []
    for player in owner_players:
        if player in db_results:
            result.append(db_results[player])
        else:
            result.append({
                "player_name": player, "team": None, "games_played": 0,
                "pts": 0, "fgm": 0, "fga": 0, "fg_pct": 0.0,
                "fg3m": 0, "fg3a": 0, "fg3_pct": 0.0,
                "ftm": 0, "fta": 0, "ft_pct": 0.0,
                "oreb": 0, "dreb": 0, "reb": 0,
                "ast": 0, "stl": 0, "blk": 0, "to_": 0,
            })

    result.sort(key=lambda r: (
        r["player_name"].split(" ", 1)[-1],
        r["player_name"]
    ))
    return result


# ── Season wrappers ───────────────────────────────────────────────────────────

def get_season_owner_game_logs(owner: str) -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_owner_game_logs(owner, LEAGUE_START, LEAGUE_END)


def get_season_owner_player_totals(owner: str) -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_owner_player_totals(owner, LEAGUE_START, LEAGUE_END)
