"""
db/queries_meta.py
──────────────────
Utility queries: last updated date, games today check, and trend indicators.
Used by the web app to populate status messages and trend arrows.
"""

from db.schema import get_connection


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
    before each pipeline run). This means trends reflect movement since the
    last game day.

    Returns a dict mapping fantasy_owner -> trend string:
        "up"   — owner improved their standing since last snapshot
        "down" — owner dropped since last snapshot
        "same" — no change in position
        "new"  — no prior snapshot exists yet (first pipeline run)
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
            trends[owner] = "up"
        elif curr_place > prev_place:
            trends[owner] = "down"
        else:
            trends[owner] = "same"

    return trends
