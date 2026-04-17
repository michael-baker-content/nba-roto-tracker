"""
backfill_matchups.py
────────────────────
One-time script to replace raw game IDs stored in the matchup column
with human-readable strings like "ORL @ PHI".

Run once from the project root with the venv active:
    python backfill_matchups.py

Safe to run multiple times — only rows whose matchup looks like a raw
game ID (all digits, 10 characters) will be updated.
"""

import time
from datetime import datetime

from nba_api.stats.endpoints import scoreboardv3

from db.schema import get_connection


def looks_like_game_id(val: str) -> bool:
    """Return True if val is a raw NBA game ID or a broken placeholder."""
    if val is None:
        return True
    s = str(val).strip()
    return (s.isdigit() and len(s) == 10) or "???" in s or s == ""


def get_matchup_for_date(game_date: str) -> dict[str, str]:
    """
    Fetch away @ home matchup strings for all games on game_date.
    game_date is a string in YYYY-MM-DD format.

    ScoreboardV3 does not include team abbreviation columns — the only
    reliable source is gameCode, formatted as "YYYYMMDD/AWYHME",
    e.g. "20260414/MIACHA" → away=MIA, home=CHA.
    """
    dt = datetime.strptime(game_date, "%Y-%m-%d")
    date_str = dt.strftime("%m/%d/%Y")

    try:
        board = scoreboardv3.ScoreboardV3(game_date=date_str, league_id="00")
        df = board.game_header.get_data_frame()
    except Exception as exc:
        print(f"  ⚠  Could not fetch scoreboard for {game_date}: {exc}")
        return {}

    result = {}
    for _, row in df.iterrows():
        game_id = str(row["gameId"])
        game_code = str(row.get("gameCode", ""))
        if "/" in game_code:
            teams = game_code.split("/")[-1]   # e.g. "MIACHA"
            if len(teams) == 6:
                away, home = teams[:3], teams[3:]
                result[game_id] = f"{away} @ {home}"
                continue
        result[game_id] = "??? @ ???"

    return result


def backfill():
    # Find all distinct (game_date, game_id) pairs where matchup is a raw ID
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT game_date, game_id, matchup
            FROM game_logs
            ORDER BY game_date
        """).fetchall()

    stale = [(r["game_date"], r["game_id"]) for r in rows
             if looks_like_game_id(r["matchup"]) or r["matchup"] == r["game_id"]]

    if not stale:
        print("✅  All matchup strings already look correct — nothing to update.")
        return

    print(f"Found {len(stale)} game(s) with raw game IDs. Fetching matchup strings…\n")

    # Group by date to minimise API calls
    by_date: dict[str, list[str]] = {}
    for game_date, game_id in stale:
        by_date.setdefault(game_date, []).append(game_id)

    total_updated = 0
    for game_date, game_ids in sorted(by_date.items()):
        print(f"  {game_date} — fetching scoreboard…")
        matchup_map = get_matchup_for_date(game_date)
        time.sleep(0.6)  # rate limit

        with get_connection() as conn:
            for game_id in game_ids:
                matchup = matchup_map.get(game_id)
                if not matchup:
                    print(f"    ⚠  No matchup found for game {game_id} — skipping")
                    continue
                conn.execute("""
                    UPDATE game_logs
                    SET matchup = :matchup
                    WHERE game_id = :game_id
                """, {"matchup": matchup, "game_id": game_id})
                print(f"    ✓  {game_id} → {matchup}")
                total_updated += 1
            conn.commit()

    print(f"\n✅  Updated {total_updated} game(s) with correct matchup strings.")


if __name__ == "__main__":
    backfill()
