"""
db/queries_standings.py — Rotisserie standings computation.

get_stat_totals()  -> raw per-owner stat aggregates
get_standings()    -> full roto leaderboard sorted by total score

All owners always appear in results. Inactive owners receive zero stats and
share the bottom score (1 point) in every category.

Scoring: best = n points, worst = 1 point. Ties share the average of spanned
values. Inactive owners always share the lowest values regardless of category
direction — a team with 0 TOs from not playing doesn't deserve the best TO rank.
"""

from config.roster import ROSTER
from config.settings import ROTO_CATEGORIES
from db.schema import get_connection

ALL_OWNERS: list[str] = sorted({p["Fantasy_Owner"] for p in ROSTER})

_ZERO_STATS: dict = {
    "pts": 0, "fg_pct": 0.0, "ft_pct": 0.0,
    "fg3m": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0, "to_": 0,
}

_TOTALS_SQL = """
SELECT
    fantasy_owner,
    SUM(pts)  AS pts,
    CASE WHEN SUM(fga) > 0 THEN CAST(SUM(fgm) AS REAL) / SUM(fga) ELSE 0 END AS fg_pct,
    CASE WHEN SUM(fta) > 0 THEN CAST(SUM(ftm) AS REAL) / SUM(fta) ELSE 0 END AS ft_pct,
    SUM(fg3m) AS fg3m,
    SUM(reb)  AS reb,
    SUM(ast)  AS ast,
    SUM(stl)  AS stl,
    SUM(blk)  AS blk,
    SUM(to_)  AS to_
FROM game_logs
WHERE fantasy_owner IN ({placeholders})
  AND game_date BETWEEN :start AND :end
  AND dnp = FALSE
GROUP BY fantasy_owner
"""


def get_stat_totals(start: str, end: str) -> list[dict]:
    """Return season aggregate stats for every owner. Missing owners get zero stats."""
    placeholders = ", ".join(f":o{i}" for i in range(len(ALL_OWNERS)))
    sql = _TOTALS_SQL.format(placeholders=placeholders)
    params = {"start": start, "end": end}
    params.update({f"o{i}": owner for i, owner in enumerate(ALL_OWNERS)})

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    db_results = {row["fantasy_owner"]: dict(row) for row in rows}
    return [
        db_results.get(owner, {"fantasy_owner": owner, **_ZERO_STATS})
        for owner in ALL_OWNERS
    ]


def _has_played(owner_data: dict) -> bool:
    """True if the owner has at least one game logged (checks multiple stats)."""
    return (
        owner_data.get("pts", 0) > 0
        or owner_data.get("fg3m", 0) > 0
        or owner_data.get("reb", 0) > 0
        or owner_data.get("ast", 0) > 0
        or owner_data.get("to_", 0) > 0
    )


def _rank_category(owners: dict, col: str, ascending: bool):
    """
    Assign roto points for one category to all owners in-place.

    Ranks go from 1 (worst) to n (best). Ties share the average of their
    spanned positions. Inactive owners always share the bottom positions
    so zero TOs from not playing never earns the best TO rank.
    """
    db_col   = "to_" if col == "TO" else col.lower()
    n_total  = len(owners)
    active   = [(o, d.get(db_col, 0)) for o, d in owners.items() if _has_played(d)]
    inactive = [(o, d.get(db_col, 0)) for o, d in owners.items() if not _has_played(d)]

    active.sort(key=lambda x: x[1], reverse=not ascending)

    i = 0
    while i < len(active):
        j = i
        while j < len(active) - 1 and active[j + 1][1] == active[i][1]:
            j += 1
        avg_pts = sum(n_total - pos for pos in range(i, j + 1)) / (j - i + 1)
        for k in range(i, j + 1):
            owners[active[k][0]][f"{col}_rank"] = avg_pts
            owners[active[k][0]][col]           = active[k][1]
        i = j + 1

    if inactive:
        avg_pts = sum(range(1, len(inactive) + 1)) / len(inactive)
        for owner_name, val in inactive:
            owners[owner_name][f"{col}_rank"] = avg_pts
            owners[owner_name][col]           = val


def get_standings(start: str, end: str) -> list[dict]:
    """Compute full roto standings. Returns all owners sorted by total score desc."""
    totals = get_stat_totals(start, end)
    owners = {row["fantasy_owner"]: dict(row) for row in totals}

    for col, _label, ascending in ROTO_CATEGORIES:
        _rank_category(owners, col, ascending)

    rank_cols = [f"{col}_rank" for col, _, _ in ROTO_CATEGORIES]
    for owner_data in owners.values():
        owner_data["total_score"] = sum(owner_data.get(rc, 0) for rc in rank_cols)

    result = sorted(owners.values(), key=lambda x: (-x["total_score"], x["fantasy_owner"]))
    for i, row in enumerate(result, start=1):
        row["place"] = i
    return result


def get_season_standings() -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_standings(LEAGUE_START, LEAGUE_END)


def get_season_stat_totals() -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_stat_totals(LEAGUE_START, LEAGUE_END)
