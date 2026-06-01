"""
db/queries_meta.py — Utility queries: last updated date and trend indicators.
"""

from db.schema import get_connection


def get_last_updated() -> str:
    """Return the most recent game date as a readable string, e.g. 'Apr 15, 2026'."""
    with get_connection() as conn:
        row = conn.execute("SELECT MAX(game_date) AS latest FROM game_logs").fetchone()
    latest = row["latest"] if row and row["latest"] else None
    if not latest:
        return "—"
    from datetime import datetime
    return datetime.strptime(latest, "%Y-%m-%d").strftime("%b %d, %Y").replace(" 0", " ")


def get_games_today() -> bool:
    """Return True if any game logs exist for today."""
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
    Compare current standings against the most recent snapshot.
    Returns {owner: "up" | "down" | "same" | "new"}.
    Snapshot is written before each pipeline run so trends reflect same-run movement.
    """
    from db.queries_standings import get_season_standings
    current = get_season_standings()
    if not current:
        return {}

    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(snapshot_date) AS latest FROM standings_snapshots"
        ).fetchone()
        latest_date = row["latest"] if row and row["latest"] else None

        if not latest_date:
            return {r["fantasy_owner"]: "new" for r in current}

        rows = conn.execute(
            "SELECT fantasy_owner, place FROM standings_snapshots WHERE snapshot_date = :d",
            {"d": latest_date}
        ).fetchall()

    prev = {r["fantasy_owner"]: r["place"] for r in rows}
    trends = {}
    for row in current:
        owner      = row["fantasy_owner"]
        prev_place = prev.get(owner)
        if prev_place is None:
            trends[owner] = "new"
        elif row["place"] < prev_place:
            trends[owner] = "up"
        elif row["place"] > prev_place:
            trends[owner] = "down"
        else:
            trends[owner] = "same"
    return trends
