"""
db/queries_standings.py
───────────────────────
Rotisserie standings computation: raw stat aggregation, per-category
ranking, and final leaderboard construction.

The two primary public functions are:

    get_stat_totals()  -> raw per-owner aggregates
    get_standings()    -> full roto leaderboard, sorted by total score

All owners are always present in results, even those with no games played.
Missing owners receive zero stats and share the bottom score (1 point) in
every category.

Scoring convention:
    Best in a category  -> n points  (e.g. 7 in a 7-team league)
    Worst in a category -> 1 point
    Tied owners share the average of their tied point values.
    Inactive owners always share the lowest available point values,
    regardless of the sort direction of the category.
"""

from config.roster import ROSTER
from config.settings import ROTO_CATEGORIES
from db.schema import get_connection


# ── Full owner list derived from the roster ───────────────────────────────────
# Built once at import time. Used to ensure every owner always appears in
# results even if they have no game logs yet.

ALL_OWNERS: list[str] = sorted({p["Fantasy_Owner"] for p in ROSTER})

_ZERO_STATS: dict = {
    "pts": 0, "fg_pct": 0.0, "ft_pct": 0.0,
    "fg3m": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0, "to_": 0,
}


# ── Raw aggregates ─────────────────────────────────────────────────────────────

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
# Note: dnp=FALSE excludes did-not-play rows from all aggregate calculations.
# A player who did not play should contribute nothing to FG%, REB, etc.


def get_stat_totals(start: str, end: str) -> list[dict]:
    """
    Return season aggregate stats for every owner between start and end dates.

    Always returns exactly len(ALL_OWNERS) rows. Owners with no game logs in
    the date range receive zero stats — they are not omitted.
    """
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


# ── Ranking helpers ────────────────────────────────────────────────────────────

def _has_played(owner_data: dict) -> bool:
    """
    Return True if this owner has at least one game logged.

    We check multiple stats rather than just pts because a player could
    theoretically score 0 points while recording rebounds, assists, etc.
    An owner is considered inactive only if ALL tracked stats are zero.
    """
    return (
        owner_data.get("pts", 0) > 0
        or owner_data.get("fg3m", 0) > 0
        or owner_data.get("reb", 0) > 0
        or owner_data.get("ast", 0) > 0
        or owner_data.get("to_", 0) > 0
    )


def _rank_category(owners: dict, col: str, ascending: bool):
    """
    Assign per-category roto points to all owners in-place.

    How points are assigned
    -----------------------
    Each owner is awarded points from 1 (worst) to n (best), where n is
    the total number of owners. The best performer gets n points; the
    worst gets 1.

    Tied owners share the average of the point values they span. For
    example, two owners tied for 1st place in a 7-team league each receive
    (7 + 6) / 2 = 6.5 points instead of both getting 7.

    ascending=False (higher is better, e.g. PTS):
        owner with most points scored -> n roto points
    ascending=True (lower is better, e.g. TO):
        owner with fewest turnovers   -> n roto points

    Inactive owners
    ---------------
    Owners with no games played are always placed at the bottom, sharing
    the lowest available point values regardless of category direction.
    This prevents an inactive owner from receiving the best TO rank simply
    because 0 turnovers looks like the "fewest" — they haven't played, so
    they don't deserve credit in any category.

    Modifies owners dict in-place, adding:
        owners[name][f"{col}_rank"] — float roto points for this category
        owners[name][col]           — the raw stat value used for ranking
    """
    db_col = "to_" if col == "TO" else col.lower()
    n_total = len(owners)

    active   = [(o, d.get(db_col, 0)) for o, d in owners.items() if _has_played(d)]
    inactive = [(o, d.get(db_col, 0)) for o, d in owners.items() if not _has_played(d)]
    n_inactive = len(inactive)

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
        avg_pts = sum(range(1, n_inactive + 1)) / n_inactive
        for owner_name, val in inactive:
            owners[owner_name][f"{col}_rank"] = avg_pts
            owners[owner_name][col]           = val


# ── Rotisserie standings ───────────────────────────────────────────────────────

def get_standings(start: str, end: str) -> list[dict]:
    """
    Compute rotisserie standings for all owners over the given date range.

    Steps:
        1. Aggregate raw stats for every owner (get_stat_totals).
        2. Rank each owner in each category (_rank_category).
        3. Sum all category ranks into a total_score.
        4. Sort by total_score descending and assign place numbers.

    All owners are always present. Owners with no games yet receive zero
    stats and the minimum points in every category.
    """
    totals = get_stat_totals(start, end)
    owners = {row["fantasy_owner"]: dict(row) for row in totals}

    for col, _label, ascending in ROTO_CATEGORIES:
        _rank_category(owners, col, ascending)

    rank_cols = [f"{col}_rank" for col, _, _ in ROTO_CATEGORIES]
    for owner_data in owners.values():
        owner_data["total_score"] = sum(owner_data.get(rc, 0) for rc in rank_cols)

    result = sorted(
        owners.values(),
        key=lambda x: (-x["total_score"], x["fantasy_owner"])
    )

    for i, row in enumerate(result, start=1):
        row["place"] = i

    return result


# ── Season wrappers ───────────────────────────────────────────────────────────

def get_season_standings() -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_standings(LEAGUE_START, LEAGUE_END)


def get_season_stat_totals() -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_stat_totals(LEAGUE_START, LEAGUE_END)
