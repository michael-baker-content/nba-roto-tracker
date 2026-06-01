"""
main.py — Daily pipeline entry point.

Usage:
    python main.py                    # today's games, DB only
    python main.py --date 2026-04-15  # backfill a specific date
    python main.py --format xlsx      # DB + file export (xlsx/csv/json)

Steps: fetch box scores → save snapshot → upsert game logs → optional export.
Snapshot is saved before game logs so trend arrows reflect same-run movement.
Re-running for the same date is safe — upserts won't create duplicates and
the snapshot is skipped if one already exists for that date.
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
from fill_missing_dnp import fill_missing_dnp

WRITERS = {
    "xlsx": (write_excel, "xlsx"),
    "csv":  (write_csv,   "csv"),
    "json": (write_json,  "json"),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Pull daily fantasy basketball game logs.")
    parser.add_argument("--date",   type=str, default=None, help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--format", type=str, default=None, choices=WRITERS.keys())
    args = parser.parse_args()
    target_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    return target_date, args.format


def main():
    target_date, fmt = parse_args()

    df = build_game_logs(target_date)
    if df.empty:
        print("No data to write.")
        return

    print(f"\n📊  {len(df)} player game log(s) found across {df['Fantasy_Owner'].nunique()} owner(s).")

    # Snapshot before game logs — captures pre-game standings for trend arrows.
    save_standings_snapshot(get_season_standings(), target_date)

    if "GAME_ID" in df.columns:
        for gid in df["GAME_ID"].unique():
            save_game_logs(df[df["GAME_ID"] == gid], target_date, str(gid))
    else:
        save_game_logs(df, target_date, f"unknown_{target_date}")

    # Fill any players omitted from the box score due to pre-game injury/rest.
    fill_missing_dnp(str(target_date))

    if fmt:
        writer, ext = WRITERS[fmt]
        writer(df, target_date, Path(f"fantasy_gamelogs_{target_date}.{ext}"))
    else:
        print("   ℹ️   No file export requested. Use --format xlsx/csv/json to export.")


if __name__ == "__main__":
    main()
