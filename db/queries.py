"""
db/queries.py
─────────────
All read queries for the web app. The two primary public functions are:

    get_standings()   -> full roto leaderboard, sorted by total score (desc)
    get_stat_totals() -> raw per-owner aggregates (used inside get_standings
                        and useful for debugging / stat detail views)

All seven owners are always present in results, even those with no games
played yet. Missing owners receive zero stats and share the bottom score
(1 point) in every category.

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
# Note: dnp=0 excludes did-not-play rows from all aggregate calculations.
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

    # Fill in zero stats for any owner not found in the database results.
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
    # SQLite stores TO as "to_" to avoid the reserved SQL keyword; map back.
    db_col = "to_" if col == "TO" else col.lower()
    n_total = len(owners)

    # Separate active and inactive owners before sorting.
    active   = [(o, d.get(db_col, 0)) for o, d in owners.items() if _has_played(d)]
    inactive = [(o, d.get(db_col, 0)) for o, d in owners.items() if not _has_played(d)]
    n_inactive = len(inactive)

    # Sort active owners so the best value comes first (index 0 = most points).
    # reverse=True  for descending (higher is better, e.g. most PTS first)
    # reverse=False for ascending  (lower is better, e.g. fewest TO first)
    active.sort(key=lambda x: x[1], reverse=not ascending)

    # Walk through active owners, grouping consecutive ties and averaging
    # the point values they span. i and j are group start/end indices.
    i = 0
    while i < len(active):
        j = i
        # Extend j forward while the next owner has the same value (a tie).
        while j < len(active) - 1 and active[j + 1][1] == active[i][1]:
            j += 1
        # Positions i+1 through j+1 (1-indexed) are tied.
        # Their point values range from (n_total - i) down to (n_total - j).
        # Average these to get each tied owner's share.
        avg_pts = sum(n_total - pos for pos in range(i, j + 1)) / (j - i + 1)
        for k in range(i, j + 1):
            owners[active[k][0]][f"{col}_rank"] = avg_pts
            owners[active[k][0]][col]           = active[k][1]
        i = j + 1

    # Inactive owners share the average of the bottom n_inactive point values
    # (always 1 through n_inactive). This keeps their total score low and
    # avoids rewarding inactivity in ascending categories like TO.
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

    Returns a list of dicts sorted by total_score descending, each containing:
        place, fantasy_owner, total_score, and for each category:
        the raw stat value and the roto points awarded (e.g. PTS_rank).
    """
    totals = get_stat_totals(start, end)   # always len(ALL_OWNERS) rows

    # Convert to a dict keyed by owner name for efficient in-place mutation.
    owners = {row["fantasy_owner"]: dict(row) for row in totals}

    # Apply roto ranking for each configured category.
    for col, _label, ascending in ROTO_CATEGORIES:
        _rank_category(owners, col, ascending)

    # Total score = sum of all category rank points.
    rank_cols = [f"{col}_rank" for col, _, _ in ROTO_CATEGORIES]
    for owner_data in owners.values():
        owner_data["total_score"] = sum(owner_data.get(rc, 0) for rc in rank_cols)

    # Sort by total score descending; break ties alphabetically by owner name.
    result = sorted(
        owners.values(),
        key=lambda x: (-x["total_score"], x["fantasy_owner"])
    )

    for i, row in enumerate(result, start=1):
        row["place"] = i

    return result


# ── Owner-specific queries ─────────────────────────────────────────────────────

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
# instead of stats. Contrast with _TOTALS_SQL above which excludes dnp=1.

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
# MAX(team) is used as an aggregate for team abbreviation. A player doesn't
# change teams during the playoffs, so MAX() always returns their actual team.
# dnp=0 ensures DNP rows don't count toward games_played or stat totals.


def get_owner_game_logs(owner: str, start: str, end: str) -> list[dict]:
    """
    Return every game log row for a given owner, most recent first.
    Includes DNP rows (flagged with dnp=1) for a complete game record.
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
            # Player is rostered but has no game logs yet.
            result.append({
                "player_name": player, "team": None, "games_played": 0,
                "pts": 0, "fgm": 0, "fga": 0, "fg_pct": 0.0,
                "fg3m": 0, "fg3a": 0, "fg3_pct": 0.0,
                "ftm": 0, "fta": 0, "ft_pct": 0.0,
                "oreb": 0, "dreb": 0, "reb": 0,
                "ast": 0, "stl": 0, "blk": 0, "to_": 0,
            })

    # Sort by last name (everything after the first space), then full name
    # as a tiebreaker for players who share a last name.
    result.sort(key=lambda r: (
        r["player_name"].split(" ", 1)[-1],
        r["player_name"]
    ))
    return result


# ── Convenience wrappers: default to full league season ───────────────────────

def get_season_standings() -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_standings(LEAGUE_START, LEAGUE_END)


def get_season_stat_totals() -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_stat_totals(LEAGUE_START, LEAGUE_END)


def get_season_owner_game_logs(owner: str) -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_owner_game_logs(owner, LEAGUE_START, LEAGUE_END)


def get_season_owner_player_totals(owner: str) -> list[dict]:
    from config.settings import LEAGUE_START, LEAGUE_END
    return get_owner_player_totals(owner, LEAGUE_START, LEAGUE_END)


def get_last_updated() -> str:
    """
    Return the most recent game_date in the database as a human-readable
    string, e.g. "Apr 15, 2026". Returns "—" if no data exists yet.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(game_date) AS latest FROM game_logs"
        ).fetchone()
    latest = row["latest"] if row and row["latest"] else None
    if not latest:
        return "—"
    from datetime import datetime
    dt = datetime.strptime(latest, "%Y-%m-%d")
    return dt.strftime("%b %d, %Y").replace(" 0", " ")


def get_games_today() -> bool:
    """Return True if any game logs exist for today's date."""
    from datetime import date
    today = str(date.today())
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM game_logs WHERE game_date = :today",
            {"today": today}
        ).fetchone()
    return (row["n"] > 0) if row else False


def get_trends() -> dict[str, str]:
    """
    Compare each owner's current standings position against their position
    on the most recent snapshot date that precedes the current standings.

    The snapshot used is always the most recent entry in standings_snapshots,
    which corresponds to the last day games were played (written by main.py
    after each pipeline run). This means trends reflect movement since the
    last game day, not necessarily since yesterday — on off days the comparison
    is still meaningful.

    Returns a dict mapping fantasy_owner -> trend string:
        "up"   — owner improved their standing since last snapshot
        "down" — owner dropped since last snapshot
        "same" — no change in position
        "new"  — no prior snapshot exists yet (first pipeline run)
    """
    current = get_season_standings()
    if not current:
        return {}

    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(snapshot_date) AS latest FROM standings_snapshots"
        ).fetchone()
        latest_date = row["latest"] if row and row["latest"] else None

        if not latest_date:
            # No snapshots have been saved yet — first pipeline run.
            return {r["fantasy_owner"]: "new" for r in current}

        rows = conn.execute(
            "SELECT fantasy_owner, place FROM standings_snapshots "
            "WHERE snapshot_date = :d",
            {"d": latest_date}
        ).fetchall()

    prev = {r["fantasy_owner"]: r["place"] for r in rows}

    trends = {}
    for row in current:
        owner = row["fantasy_owner"]
        curr_place = row["place"]
        prev_place = prev.get(owner)
        if prev_place is None:
            trends[owner] = "new"
        elif curr_place < prev_place:
            # Lower place number = better position (1st is best).
            trends[owner] = "up"
        elif curr_place > prev_place:
            trends[owner] = "down"
        else:
            trends[owner] = "same"

    return trends
