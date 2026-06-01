"""
nba/boxscore.py — Fetches and processes NBA box scores.

V3 endpoints only (BoxScoreTraditionalV3) — V2 returns empty data for current seasons.
GAME_ID is the raw NBA key used for DB upserts; MATCHUP is the display string ("MIA @ CHA").
DNP players are stored with dnp=True and zeroed stats rather than omitted.
"""

import time
from datetime import date

import pandas as pd
from nba_api.stats.endpoints import boxscoretraditionalv3

from config.roster import ROSTER, STAT_COLS, PCT_COLS
from nba.scoreboard import get_started_game_ids, get_matchup_map


def fetch_box_score(game_id: str, delay: float = 0.6) -> pd.DataFrame:
    """
    Fetch box score for one game. The delay guards against NBA.com rate limits —
    increase it if you encounter frequent timeouts on a cloud server.
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
    Fetch all started/completed games for target_date, filter to drafted players,
    and return a tidy DataFrame ready for storage. Returns empty DataFrame if no
    games have started or no drafted players appear in any box score.
    """
    roster_df   = pd.DataFrame(ROSTER)
    drafted_ids = set(roster_df["PLAYER_ID"])

    print(f"📅  Fetching games for {target_date} …")

    game_ids = get_started_game_ids(target_date)
    if not game_ids:
        print("   No started or completed games found for this date.")
        return pd.DataFrame()

    print(f"   Found {len(game_ids)} game(s): {game_ids}")

    matchup_map = get_matchup_map(target_date)

    all_rows = []
    for gid in game_ids:
        print(f"   → box score {gid} …")
        df = fetch_box_score(gid)
        if df.empty:
            continue
        all_rows.append(df[df["personId"].isin(drafted_ids)].copy())

    if not all_rows:
        print("   No drafted players found in today's box scores.")
        return pd.DataFrame()

    combined = pd.concat(all_rows, ignore_index=True)
    combined = combined.rename(columns={"personId": "PLAYER_ID"})
    combined = combined.merge(roster_df[["PLAYER_ID", "Fantasy_Owner"]], on="PLAYER_ID", how="left")

    # V3 uses camelCase — translate to internal ALL_CAPS. Prefixed _ columns are dropped below.
    col_map = {
        "firstName": "_firstName", "familyName": "_familyName",
        "teamTricode": "TEAM", "PLAYER_ID": "PLAYER_ID",
        "Fantasy_Owner": "Fantasy_Owner", "gameId": "GAME_ID", "comment": "_comment",
        "points": "PTS", "fieldGoalsMade": "FGM", "fieldGoalsAttempted": "FGA",
        "threePointersMade": "FG3M", "threePointersAttempted": "FG3A",
        "freeThrowsMade": "FTM", "freeThrowsAttempted": "FTA",
        "reboundsOffensive": "OREB", "reboundsDefensive": "DREB", "reboundsTotal": "REB",
        "assists": "AST", "turnovers": "TO", "steals": "STL", "blocks": "BLK",
    }
    available = {k: v for k, v in col_map.items() if k in combined.columns}
    result = combined[list(available.keys())].rename(columns=available)

    result["PLAYER"] = (result["_firstName"] + " " + result["_familyName"]).str.strip()
    result = result.drop(columns=["_firstName", "_familyName"])

    # comment field: "DNP - COACH'S DECISION", "DND - INJURY/ILLNESS", "NWT" = did not play.
    if "_comment" in result.columns:
        result["DNP"] = result["_comment"].apply(
            lambda c: bool(c and str(c).strip().upper().startswith(("DNP", "DND", "NWT")))
        )
        result = result.drop(columns=["_comment"])
    else:
        result["DNP"] = False

    result["MATCHUP"] = result["GAME_ID"].map(matchup_map).fillna(result["GAME_ID"])
    result = result.sort_values(["Fantasy_Owner", "PLAYER"]).reset_index(drop=True)

    # Zero DNP stats so they don't contribute to cumulative totals or percentages.
    dnp_mask = result["DNP"]
    for col in STAT_COLS:
        if col in result.columns:
            result.loc[dnp_mask, col] = 0
            result[col] = result[col].fillna(0).astype(int)

    result["FG_PCT"]  = result.apply(lambda r: r["FGM"]  / r["FGA"]  if r["FGA"]  > 0 else 0.0, axis=1)
    result["FG3_PCT"] = result.apply(lambda r: r["FG3M"] / r["FG3A"] if r["FG3A"] > 0 else 0.0, axis=1)
    result["FT_PCT"]  = result.apply(lambda r: r["FTM"]  / r["FTA"]  if r["FTA"]  > 0 else 0.0, axis=1)

    return result
