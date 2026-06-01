"""
db/queries_leaders.py — Statistical leaders (top N players per category).

Counting stats are simple cumulative sums. Percentage stats and turnovers
use a games-played threshold that activates once any player reaches 6 games,
keeping the page populated early in a new season.

Category order: PTS → FG% → 3PM → FT% → REB → AST → STL → BLK → TO/game
"""

from db.schema import get_connection


def get_stat_leaders(start: str, end: str, top_n: int = 5) -> dict:
    """
    Return top N players per category as an ordered dict.
    Each value is a list of {player_name, fantasy_owner, team, value, display}.
    """
    with get_connection() as conn:
        row = conn.execute("""
            SELECT MAX(gp) AS max_gp FROM (
                SELECT COUNT(*) AS gp FROM game_logs
                WHERE game_date BETWEEN :start AND :end AND dnp = FALSE
                GROUP BY player_name
            ) sub
        """, {"start": start, "end": end}).fetchone()
    max_gp = row["max_gp"] if row and row["max_gp"] else 0
    MIN_GP = 4 if max_gp >= 6 else 1
    pct_suffix = " (>4 games played)" if MIN_GP >= 4 else ""

    counting_cats = [
        ("PTS",  "pts",  "Points"),
        ("FG3M", "fg3m", "3-Pointers Made"),
        ("REB",  "reb",  "Rebounds"),
        ("AST",  "ast",  "Assists"),
        ("STL",  "stl",  "Steals"),
        ("BLK",  "blk",  "Blocks"),
    ]

    result = {}

    with get_connection() as conn:
        for _key, col_name, label in counting_cats:
            rows = conn.execute(f"""
                SELECT player_name, fantasy_owner, MAX(team) AS team, SUM({col_name}) AS total
                FROM game_logs
                WHERE game_date BETWEEN :start AND :end AND dnp = FALSE
                GROUP BY player_name, fantasy_owner
                ORDER BY total DESC LIMIT :n
            """, {"start": start, "end": end, "n": top_n}).fetchall()
            result[label] = [
                {"player_name": r["player_name"], "fantasy_owner": r["fantasy_owner"],
                 "team": r["team"] or "—", "value": int(r["total"] or 0),
                 "display": str(int(r["total"] or 0))}
                for r in rows
            ]

        for col, pct_col, label_base in [
            ("fgm", "fga", f"Field Goal %{pct_suffix}"),
            ("ftm", "fta", f"Free Throw %{pct_suffix}"),
        ]:
            rows = conn.execute(f"""
                SELECT player_name, fantasy_owner, MAX(team) AS team,
                    CAST(SUM({col}) AS REAL) / NULLIF(SUM({pct_col}), 0) AS pct
                FROM game_logs
                WHERE game_date BETWEEN :start AND :end AND dnp = FALSE
                GROUP BY player_name, fantasy_owner
                HAVING COUNT(*) >= :min_gp
                ORDER BY pct DESC LIMIT :n
            """, {"start": start, "end": end, "min_gp": MIN_GP, "n": top_n}).fetchall()
            result[label_base] = [
                {"player_name": r["player_name"], "fantasy_owner": r["fantasy_owner"],
                 "team": r["team"] or "—", "value": round((r["pct"] or 0) * 100, 1),
                 "display": f"{round((r['pct'] or 0) * 100, 1)}%"}
                for r in rows
            ]

        # Turnovers per game — fewer is better
        rows = conn.execute("""
            SELECT player_name, fantasy_owner, MAX(team) AS team,
                CAST(SUM(to_) AS REAL) / NULLIF(COUNT(*), 0) AS to_pg
            FROM game_logs
            WHERE game_date BETWEEN :start AND :end AND dnp = FALSE
            GROUP BY player_name, fantasy_owner
            HAVING COUNT(*) >= :min_gp
            ORDER BY to_pg ASC LIMIT :n
        """, {"start": start, "end": end, "min_gp": MIN_GP, "n": top_n}).fetchall()
        result[f"Turnovers per Game{pct_suffix}"] = [
            {"player_name": r["player_name"], "fantasy_owner": r["fantasy_owner"],
             "team": r["team"] or "—", "value": round(r["to_pg"] or 0, 1),
             "display": str(round(r["to_pg"] or 0, 1))}
            for r in rows
        ]

    ordered_keys = [
        "Points", f"Field Goal %{pct_suffix}", "3-Pointers Made",
        f"Free Throw %{pct_suffix}", "Rebounds", "Assists", "Steals", "Blocks",
        f"Turnovers per Game{pct_suffix}",
    ]
    return {k: result[k] for k in ordered_keys if k in result}


def get_season_stat_leaders() -> dict:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_stat_leaders(LEAGUE_START, LEAGUE_END)
