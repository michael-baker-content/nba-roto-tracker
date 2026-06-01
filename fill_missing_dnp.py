"""
fill_missing_dnp.py — Insert DNP rows for rostered players omitted from box scores.

When a player is ruled out before tip-off, the NBA API omits them entirely
rather than listing them as DNP. This script detects those gaps and inserts
DNP rows so the game log shows a complete record.

For each game date:
    1. Find which teams played and their game IDs/matchups.
    2. Look up each rostered player's current team from their most recent
       game log entry (no TEAM field required in roster.py).
    3. Insert a DNP row for any rostered player whose team played but has
       no row for that date.

Safe to re-run — uses ON CONFLICT DO NOTHING so existing rows are untouched.
Also called automatically at the end of main.py after each pipeline run.

Usage:
    python fill_missing_dnp.py                    # fix all dates in DB
    python fill_missing_dnp.py --date 2026-05-28  # fix a specific date
"""

import argparse
from db.schema import get_connection
from config.roster import ROSTER


def get_player_teams(conn) -> dict[int, tuple[str, str]]:
    """
    Return {player_id: (team, fantasy_owner)} derived from the most recent
    non-DNP game log entry for each rostered player.

    Players with no game logs yet are excluded — they haven't played and
    we don't know their team yet.
    """
    player_ids = [p["PLAYER_ID"] for p in ROSTER]
    placeholders = ", ".join(str(pid) for pid in player_ids)
    rows = conn.execute(f"""
        SELECT player_id, fantasy_owner, team
        FROM game_logs
        WHERE player_id IN ({placeholders})
          AND dnp = FALSE
          AND team IS NOT NULL
          AND team != ''
        ORDER BY game_date DESC
    """).fetchall()

    # First occurrence per player_id is their most recent team
    seen: dict[int, tuple[str, str]] = {}
    for r in rows:
        pid = r["player_id"]
        if pid not in seen:
            seen[pid] = (r["team"], r["fantasy_owner"])
    return seen


def get_game_info_for_date(conn, game_date: str) -> list[dict]:
    """
    Return one entry per game on game_date: {game_id, matchup, teams}.
    Teams is the set of tricodes that appear in box scores for that game.
    """
    rows = conn.execute("""
        SELECT DISTINCT game_id, matchup, team
        FROM game_logs
        WHERE game_date = :d
    """, {"d": game_date}).fetchall()

    games: dict[str, dict] = {}
    for r in rows:
        gid = r["game_id"]
        if gid not in games:
            games[gid] = {"matchup": r["matchup"], "teams": set()}
        if r["team"]:
            games[gid]["teams"].add(r["team"])

    return [{"game_id": gid, **info} for gid, info in games.items()]


def get_existing_player_ids(conn, game_date: str, game_id: str) -> set[int]:
    """Return player_ids already recorded for this game."""
    rows = conn.execute("""
        SELECT player_id FROM game_logs
        WHERE game_date = :d AND game_id = :gid
    """, {"d": game_date, "gid": game_id}).fetchall()
    return {r["player_id"] for r in rows}


def insert_dnp_row(conn, game_date: str, game_id: str, matchup: str,
                   player_id: int, player_name: str, team: str, owner: str):
    conn.execute("""
        INSERT INTO game_logs
            (game_date, game_id, fantasy_owner, player_id, player_name,
             team, matchup, dnp,
             pts, fgm, fga, fg_pct, fg3m, fg3a, fg3_pct,
             ftm, fta, ft_pct, oreb, dreb, reb, ast, stl, blk, to_)
        VALUES
            (:date, :gid, :owner, :pid, :name,
             :team, :matchup, TRUE,
             0, 0, 0, 0.0, 0, 0, 0.0, 0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0)
        ON CONFLICT (game_date, game_id, player_id) DO NOTHING
    """, {
        "date": game_date, "gid": game_id, "owner": owner,
        "pid": player_id, "name": player_name,
        "team": team, "matchup": matchup,
    })


def fill_missing_dnp(game_date: str | None = None):
    # Build player_id -> player_name lookup from roster
    roster_by_id = {p["PLAYER_ID"]: p["PLAYER"] for p in ROSTER}

    with get_connection() as conn:
        # Derive current team for each player from their game log history
        player_teams = get_player_teams(conn)

        # Build team -> [player_ids] index
        team_to_players: dict[str, list[int]] = {}
        for pid, (team, _owner) in player_teams.items():
            team_to_players.setdefault(team, []).append(pid)

        # Determine which dates to process
        if game_date:
            dates = [game_date]
        else:
            rows = conn.execute(
                "SELECT DISTINCT game_date FROM game_logs ORDER BY game_date"
            ).fetchall()
            dates = [r["game_date"] for r in rows]

        total_inserted = 0

        for d in dates:
            games = get_game_info_for_date(conn, d)
            for game in games:
                gid      = game["game_id"]
                matchup  = game["matchup"]
                teams    = game["teams"]
                existing = get_existing_player_ids(conn, d, gid)

                for team in teams:
                    for pid in team_to_players.get(team, []):
                        if pid not in existing:
                            player_name = roster_by_id.get(pid, f"Player {pid}")
                            _team, owner = player_teams[pid]
                            insert_dnp_row(conn, d, gid, matchup,
                                           pid, player_name, team, owner)
                            print(f"   + DNP: {player_name} ({team}) on {d}")
                            total_inserted += 1

        conn.commit()

    if total_inserted:
        print(f"\n✅  Inserted {total_inserted} missing DNP row(s).")
    else:
        print("✅  No missing DNP rows found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fill missing DNP rows for rostered players omitted from box scores."
    )
    parser.add_argument("--date", type=str, default=None,
                        help="YYYY-MM-DD. Defaults to all dates in the database.")
    args = parser.parse_args()
    fill_missing_dnp(args.date)
