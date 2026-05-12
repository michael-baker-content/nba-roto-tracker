"""
db/queries_leaders.py
─────────────────────
Statistical leaders queries: top N players per category across the season.
Used by the leaders page (/leaders).

Counting stats (PTS, FG3M, REB, AST, STL, BLK) are simple cumulative sums.
Percentage stats (FG%, FT%) and turnovers use a games-played threshold to
filter out statistical noise. The threshold activates once any player has
accumulated 6+ games, keeping the page populated early in a new season.
"""

from db.schema import get_connection


def get_stat_leaders(start: str, end: str, top_n: int = 5) -> dict:
    """
    Return the top N players in each statistical category.

    Returns a dict keyed by category label, each value a list of dicts:
        [{"player_name", "fantasy_owner", "team", "value", "display"}, ...]
    Categories are returned in display order:
        PTS → FG% → 3PM → FT% → REB → AST → STL → BLK → TO
    """
    # Check max games played to determine whether to apply the threshold.
    # Below 6 games, MIN_GP=1 so all players qualify and the page stays useful
    # early in a new season. At 6+ games, MIN_GP=4 filters statistical noise.
    with get_connection() as conn:
        row = conn.execute("""
            SELECT MAX(gp) AS max_gp FROM (
                SELECT COUNT(*) AS gp
                FROM game_logs
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
        # ── Counting stats ────────────────────────────────────────────────────
        for col_key, col_name, label in counting_cats:
            rows = conn.execute(f"""
                SELECT
                    player_name,
                    fantasy_owner,
                    MAX(team)        AS team,
                    SUM({col_name})  AS total
                FROM game_logs
                WHERE game_date BETWEEN :start AND :end
                  AND dnp = FALSE
                GROUP BY player_name, fantasy_owner
                ORDER BY total DESC
                LIMIT :n
            """, {"start": start, "end": end, "n": top_n}).fetchall()

            result[label] = [
                {
                    "player_name":   r["player_name"],
                    "fantasy_owner": r["fantasy_owner"],
                    "team":          r["team"] or "—",
                    "value":         int(r["total"] or 0),
                    "display":       str(int(r["total"] or 0)),
                }
                for r in rows
            ]

        # ── FG% ───────────────────────────────────────────────────────────────
        rows = conn.execute("""
            SELECT
                player_name,
                fantasy_owner,
                MAX(team)                                    AS team,
                COUNT(*)                                     AS games_played,
                CAST(SUM(fgm) AS REAL) / NULLIF(SUM(fga),0) AS fg_pct
            FROM game_logs
            WHERE game_date BETWEEN :start AND :end
              AND dnp = FALSE
            GROUP BY player_name, fantasy_owner
            HAVING COUNT(*) >= :min_gp
            ORDER BY fg_pct DESC
            LIMIT :n
        """, {"start": start, "end": end, "min_gp": MIN_GP, "n": top_n}).fetchall()

        result[f"Field Goal %{pct_suffix}"] = [
            {
                "player_name":   r["player_name"],
                "fantasy_owner": r["fantasy_owner"],
                "team":          r["team"] or "—",
                "value":         round((r["fg_pct"] or 0) * 100, 1),
                "display":       f"{round((r['fg_pct'] or 0) * 100, 1)}%",
            }
            for r in rows
        ]

        # ── FT% ───────────────────────────────────────────────────────────────
        rows = conn.execute("""
            SELECT
                player_name,
                fantasy_owner,
                MAX(team)                                    AS team,
                COUNT(*)                                     AS games_played,
                CAST(SUM(ftm) AS REAL) / NULLIF(SUM(fta),0) AS ft_pct
            FROM game_logs
            WHERE game_date BETWEEN :start AND :end
              AND dnp = FALSE
            GROUP BY player_name, fantasy_owner
            HAVING COUNT(*) >= :min_gp
            ORDER BY ft_pct DESC
            LIMIT :n
        """, {"start": start, "end": end, "min_gp": MIN_GP, "n": top_n}).fetchall()

        result[f"Free Throw %{pct_suffix}"] = [
            {
                "player_name":   r["player_name"],
                "fantasy_owner": r["fantasy_owner"],
                "team":          r["team"] or "—",
                "value":         round((r["ft_pct"] or 0) * 100, 1),
                "display":       f"{round((r['ft_pct'] or 0) * 100, 1)}%",
            }
            for r in rows
        ]

        # ── TO ascending ──────────────────────────────────────────────────────
        rows = conn.execute("""
            SELECT
                player_name,
                fantasy_owner,
                MAX(team)   AS team,
                COUNT(*)    AS games_played,
                SUM(to_)    AS total_to
            FROM game_logs
            WHERE game_date BETWEEN :start AND :end
              AND dnp = FALSE
            GROUP BY player_name, fantasy_owner
            HAVING COUNT(*) >= :min_gp
            ORDER BY total_to ASC
            LIMIT :n
        """, {"start": start, "end": end, "min_gp": MIN_GP, "n": top_n}).fetchall()

        result[f"Turnovers{pct_suffix}"] = [
            {
                "player_name":   r["player_name"],
                "fantasy_owner": r["fantasy_owner"],
                "team":          r["team"] or "—",
                "value":         int(r["total_to"] or 0),
                "display":       str(int(r["total_to"] or 0)),
            }
            for r in rows
        ]

    # Return in display order: PTS → FG% → 3PM → FT% → REB → AST → STL → BLK → TO
    ordered_keys = [
        "Points",
        f"Field Goal %{pct_suffix}",
        "3-Pointers Made",
        f"Free Throw %{pct_suffix}",
        "Rebounds",
        "Assists",
        "Steals",
        "Blocks",
        f"Turnovers{pct_suffix}",
    ]
    return {k: result[k] for k in ordered_keys if k in result}


def get_season_stat_leaders() -> dict:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_stat_leaders(LEAGUE_START, LEAGUE_END)

