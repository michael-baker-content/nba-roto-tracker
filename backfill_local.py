"""
backfill_local.py — Fetch all missing game dates into the local SQLite database.

Checks which dates already exist in the local DB and fetches only the missing
ones from the NBA API. Skips today's date since tonight's games may not be final.

Usage:
    python backfill_local.py
"""

from datetime import date, timedelta
from db.schema import get_connection
from db.queries import get_season_standings
from db.store import save_game_logs, save_standings_snapshot
from nba.boxscore import build_game_logs
from config.settings import LEAGUE_START


def get_existing_dates() -> set[str]:
    """Return all game_dates already in the local database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT game_date FROM game_logs").fetchall()
    return {row["game_date"] for row in rows}


def date_range(start_str: str, end_date: date):
    """Yield each date from start_str up to but not including end_date."""
    current = date.fromisoformat(start_str)
    while current < end_date:
        yield current
        current += timedelta(days=1)


def main():
    existing  = get_existing_dates()
    today     = date.today()
    missing   = [
        d for d in date_range(LEAGUE_START, date(2026, 5, 29))
        if str(d) not in existing
    ]

    if not missing:
        print("✅  Local database is already up to date.")
        return

    print(f"Found {len(missing)} date(s) to backfill: {[str(d) for d in missing]}\n")

    for d in missing:
        for attempt in range(1, 4):  # up to 3 attempts per date
            try:
                df = build_game_logs(d)
                break
            except Exception as exc:
                if attempt < 3:
                    print(f"   ⚠  Attempt {attempt} failed for {d}: {exc}. Retrying in 10s…")
                    import time; time.sleep(10)
                else:
                    print(f"   ❌  Skipping {d} after 3 failed attempts: {exc}\n")
                    df = None
                    break

        if df is None:
            continue
        if df.empty:
            print(f"   ⏭  No data for {d} — skipping.\n")
            continue
        save_standings_snapshot(get_season_standings(), d)
        for gid in df["GAME_ID"].unique():
            save_game_logs(df[df["GAME_ID"] == gid], d, str(gid))
        print(f"   ✅  {d} saved ({len(df)} rows).\n")

    print("Done.")


if __name__ == "__main__":
    main()
