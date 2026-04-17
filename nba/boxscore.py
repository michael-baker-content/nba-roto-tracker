"""
nba/boxscore.py
───────────────
Fetches player-level box score data from the NBA Stats API and transforms
it into a clean DataFrame ready for storage.

Key design decisions worth knowing:

  V3 endpoints only — BoxScoreTraditionalV3 is required for the 2025-26
  season and beyond. The older V2 endpoint returns empty data for current
  season games. Column names in V3 are camelCase (e.g. "fieldGoalsMade")
  rather than the ALL_CAPS used in V2, hence the col_map translation below.

  GAME_ID vs MATCHUP — these are two separate columns in the output DataFrame.
  GAME_ID holds the raw NBA game ID (e.g. "0052500111"), used as the database
  key for upserts. MATCHUP holds the human-readable string (e.g. "MIA @ CHA"),
  used for display in the owner page game log. They start from the same source
  but serve different purposes and must not be conflated.

  DNP handling — a player appearing in the box score with a non-empty comment
  field (e.g. "DNP - COACH'S DECISION") did not play. We store these rows with
  a dnp=True flag and zeroed stats rather than omitting them, so the owner page
  can show an honest record of every game a player was rostered.
"""

import time
from datetime import date

import pandas as pd
from nba_api.stats.endpoints import boxscoretraditionalv3

from config.roster import ROSTER, STAT_COLS, PCT_COLS
from nba.scoreboard import get_started_game_ids, get_matchup_map


def fetch_box_score(game_id: str, delay: float = 0.6) -> pd.DataFrame:
    """
    Fetch the player-level traditional box score for one game.

    The delay parameter (default 0.6s) is a courtesy sleep before each
    request. NBA.com rate-limits by IP address — cloud server IPs are more
    likely to be throttled than residential ones. Increase this value if
    you encounter frequent API failures after deploying.
    """
    time.sleep(delay)
    try:
        box = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        df = box.player_stats.get_data_frame()
        df["gameId"] = game_id
        return df
    except Exception as exc:
        print(f"  ⚠  Could not fetch game {game_id}: {exc}")
        return pd.DataFrame()


def build_game_logs(target_date: date) -> pd.DataFrame:
    """
    Fetch all started/completed games for target_date, filter to players
    drafted by league owners, and return a tidy DataFrame with fantasy
    metadata attached.

    Returns an empty DataFrame if no games have started or no drafted
    players appear in any box score.

    Column reference for the returned DataFrame:
        GAME_ID       — raw NBA game ID (used as DB key, not displayed)
        MATCHUP       — human-readable string, e.g. "MIA @ CHA"
        PLAYER        — full player name (assembled from firstName + familyName)
        TEAM          — player's team tricode, e.g. "OKC"
        Fantasy_Owner — owner name from config/roster.py
        DNP           — True if the player did not play (see DNP note above)
        PTS, FGM, FGA, FG3M, FG3A, FTM, FTA, OREB, DREB, REB, AST, STL, BLK, TO
                      — integer counting stats (zeroed for DNP players)
        FG_PCT, FG3_PCT, FT_PCT
                      — calculated percentages as decimals (0.0–1.0)
    """
    roster_df = pd.DataFrame(ROSTER)
    drafted_ids = set(roster_df["PLAYER_ID"])

    print(f"📅  Fetching games for {target_date} …")

    # get_started_game_ids filters out gameStatus=1 (not yet tipped off),
    # preventing errors from fetching box scores for future games.
    game_ids = get_started_game_ids(target_date)
    if not game_ids:
        print("   No started or completed games found for this date.")
        return pd.DataFrame()

    print(f"   Found {len(game_ids)} game(s): {game_ids}")

    # Fetch all matchup strings in one scoreboard call rather than deriving
    # them per-game, to minimise total API requests.
    matchup_map = get_matchup_map(target_date)

    all_rows = []
    for gid in game_ids:
        print(f"   → box score {gid} …")
        df = fetch_box_score(gid)
        if df.empty:
            continue
        # Filter to only players on someone's fantasy roster.
        # personId in V3 corresponds to PLAYER_ID in our roster.
        drafted_rows = df[df["personId"].isin(drafted_ids)].copy()
        all_rows.append(drafted_rows)

    if not all_rows:
        print("   No drafted players found in today's box scores.")
        return pd.DataFrame()

    combined = pd.concat(all_rows, ignore_index=True)

    # Rename before merging so the join key (PLAYER_ID) matches roster_df.
    combined = combined.rename(columns={"personId": "PLAYER_ID"})
    combined = combined.merge(
        roster_df[["PLAYER_ID", "Fantasy_Owner"]],
        on="PLAYER_ID", how="left"
    )

    # Translate V3 camelCase column names to our internal ALL_CAPS convention.
    # Columns prefixed with _ are intermediate values dropped after processing.
    # gameId is kept as GAME_ID (the DB key) separately from MATCHUP (display).
    col_map = {
        "firstName":              "_firstName",
        "familyName":             "_familyName",
        "teamTricode":            "TEAM",
        "PLAYER_ID":              "PLAYER_ID",
        "Fantasy_Owner":          "Fantasy_Owner",
        "gameId":                 "GAME_ID",
        "comment":                "_comment",
        "points":                 "PTS",
        "fieldGoalsMade":         "FGM",
        "fieldGoalsAttempted":    "FGA",
        "threePointersMade":      "FG3M",
        "threePointersAttempted": "FG3A",
        "freeThrowsMade":         "FTM",
        "freeThrowsAttempted":    "FTA",
        "reboundsOffensive":      "OREB",
        "reboundsDefensive":      "DREB",
        "reboundsTotal":          "REB",
        "assists":                "AST",
        "turnovers":              "TO",
        "steals":                 "STL",
        "blocks":                 "BLK",
    }
    available = {k: v for k, v in col_map.items() if k in combined.columns}
    result = combined[list(available.keys())].rename(columns=available)

    # V3 splits the player name into firstName and familyName; reassemble here.
    result["PLAYER"] = (result["_firstName"] + " " + result["_familyName"]).str.strip()
    result = result.drop(columns=["_firstName", "_familyName"])

    # DNP detection: V3 populates the comment field with strings like
    # "DNP - COACH'S DECISION" or "DND - INJURY/ILLNESS" for non-playing
    # players. "NWT" (Not With Team) also indicates no participation.
    # We flag these rows rather than dropping them so the owner page can
    # display an honest record of every game a player was available.
    if "_comment" in result.columns:
        result["DNP"] = result["_comment"].apply(
            lambda c: bool(c and str(c).strip().upper().startswith(("DNP", "DND", "NWT")))
        )
        result = result.drop(columns=["_comment"])
    else:
        result["DNP"] = False

    # MATCHUP is the display string (e.g. "MIA @ CHA"). GAME_ID is kept
    # separately as the stable database key. If the matchup lookup fails
    # for any reason, fall back to the raw game ID rather than crashing.
    result["MATCHUP"] = result["GAME_ID"].map(matchup_map).fillna(result["GAME_ID"])

    result = result.sort_values(["Fantasy_Owner", "PLAYER"]).reset_index(drop=True)

    # Zero out all counting stats for DNP players so they cannot
    # accidentally contribute to cumulative totals or percentage calculations.
    dnp_mask = result["DNP"]
    for col in STAT_COLS:
        if col in result.columns:
            result.loc[dnp_mask, col] = 0
            result[col] = result[col].fillna(0).astype(int)

    # Percentages are calculated from the (now zeroed) counting stats.
    # A player with 0 attempts receives 0.0% rather than a division error.
    result["FG_PCT"]  = result.apply(lambda r: r["FGM"]  / r["FGA"]  if r["FGA"]  > 0 else 0.0, axis=1)
    result["FG3_PCT"] = result.apply(lambda r: r["FG3M"] / r["FG3A"] if r["FG3A"] > 0 else 0.0, axis=1)
    result["FT_PCT"]  = result.apply(lambda r: r["FTM"]  / r["FTA"]  if r["FTA"]  > 0 else 0.0, axis=1)

    return result
