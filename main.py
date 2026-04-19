"""
main.py
───────
Daily pipeline entry point. Run this once per day after NBA games complete.

Pipeline steps (in order):
    1. Fetch box scores from the NBA Stats API for the target date
    2. Filter to drafted players and build game log rows
    3. Upsert game logs into the database (safe to re-run for the same date)
    4. Save a standings snapshot (used for trend indicators on the leaderboard)
    5. Optionally export a file (xlsx / csv / json)

The database is always updated regardless of whether a file is exported.
Steps 1–4 are idempotent — running the pipeline twice for the same date
updates existing rows rather than creating duplicates.

Usage:
    python main.py                              # fetch today's games, DB only
    python main.py --date 2026-04-15            # backfill a specific date
    python main.py --format xlsx                # DB + Excel export
    python main.py --format csv                 # DB + CSV export
    python main.py --format json                # DB + JSON export
    python main.py --date 2026-04-14 --format csv
"""

import argparse
from datetime import date, datetime
from pathlib import Path

from nba.boxscore import build_game_logs
from db.store import save_game_logs, save_standings_snapshot
from db.queries import get_season_standings
from output.excel_writer import write_excel
from output.csv_writer import write_csv
from output.json_writer import write_json


# Maps --format argument values to (writer_function, file_extension) pairs.
WRITERS = {
    "xlsx": (write_excel, "xlsx"),
    "csv":  (write_csv,   "csv"),
    "json": (write_json,  "json"),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Pull daily fantasy basketball game logs.")
    parser.add_argument(
        "--date", type=str, default=None,
        help="Date to pull in YYYY-MM-DD format. Defaults to today."
    )
    parser.add_argument(
        "--format", type=str, default=None, choices=WRITERS.keys(),
        help="Optionally export a file in addition to updating the database."
    )
    args = parser.parse_args()
    target_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    return target_date, args.format


def main():
    target_date, fmt = parse_args()

    # ── Step 1 & 2: Fetch box scores and build game log DataFrame ─────────────
    df = build_game_logs(target_date)
    if df.empty:
        print("No data to write.")
        return

    print(f"\n📊  {len(df)} player game log(s) found across "
          f"{df['Fantasy_Owner'].nunique()} owner(s).")

    # ── Step 3: Save standings snapshot BEFORE updating game logs ─────────────
    # Capturing standings before tonight's games are stored means the snapshot
    # reflects the "before" state — so trend arrows show meaningful movement
    # immediately after the pipeline runs rather than requiring a second run.
    # If a snapshot already exists for this date (e.g. pipeline re-run), it is
    # skipped so the before/after comparison remains intact.
    standings = get_season_standings()
    save_standings_snapshot(standings, target_date)

    # ── Step 4: Upsert game logs into the database ────────────────────────────
    # Split by GAME_ID so each game is saved as a separate batch. This keeps
    # the upsert logic clean and makes partial re-runs easy to reason about.
    # MATCHUP (human-readable, e.g. "ORL @ PHI") is stored separately from
    # GAME_ID (the NBA database key) — see nba/boxscore.py for details.
    if "GAME_ID" in df.columns:
        for gid in df["GAME_ID"].unique():
            save_game_logs(df[df["GAME_ID"] == gid], target_date, str(gid))
    else:
        save_game_logs(df, target_date, f"unknown_{target_date}")

    # ── Step 5: Optional file export ─────────────────────────────────────────
    if fmt:
        writer, ext = WRITERS[fmt]
        out_path = Path(f"fantasy_gamelogs_{target_date}.{ext}")
        writer(df, target_date, out_path)
    else:
        print("   ℹ️   No file export requested. Use --format xlsx/csv/json to export.")


if __name__ == "__main__":
    main()
