from datetime import date

from nba_api.stats.endpoints import scoreboardv3


def get_game_ids(target_date: date) -> list[str]:
    """Return all NBA game IDs scheduled for target_date."""
    date_str = target_date.strftime("%Y-%m-%d")
    board = scoreboardv3.ScoreboardV3(game_date=date_str, league_id="00")
    df = board.game_header.get_data_frame()
    return df["gameId"].tolist()


def get_started_game_ids(target_date: date) -> list[str]:
    """
    Return only game IDs for games that have started or completed today.
    Filters out games with gameStatus == 1 (scheduled, not yet started).

    ScoreboardV3 gameStatus values:
        1 = scheduled / pre-game
        2 = in progress
        3 = final
    """
    date_str = target_date.strftime("%Y-%m-%d")
    board = scoreboardv3.ScoreboardV3(game_date=date_str, league_id="00")
    df = board.game_header.get_data_frame()

    started = df[df["gameStatus"] != 1]
    skipped = df[df["gameStatus"] == 1]

    for _, row in skipped.iterrows():
        print(f"   ⏭  Skipping {row['gameId']} — game has not started yet")

    return started["gameId"].tolist()

    started = df[df["gameStatus"] != 1]
    skipped = df[df["gameStatus"] == 1]

    for _, row in skipped.iterrows():
        print(f"   ⏭  Skipping {row['gameId']} — game has not started yet")

    return started["gameId"].tolist()


def _extract_tricode(row, away_or_home: str) -> str:
    """
    Extract a team tricode from a ScoreboardV3 game header row.

    ScoreboardV3 does not provide separate team abbreviation columns.
    The only reliable source is gameCode, which has the format:
        YYYYMMDD/AWYHME  e.g. "20260414/MIACHA"
    where the 6 characters after the slash are away (3) + home (3).
    """
    game_code = str(row.get("gameCode", ""))
    if "/" in game_code:
        teams = game_code.split("/")[-1]   # e.g. "MIACHA"
        if len(teams) == 6:
            return teams[:3] if away_or_home == "away" else teams[3:]

    return "???"


def get_matchup_map(target_date: date) -> dict[str, str]:
    """
    Return a mapping of game_id -> matchup string for target_date.
    Format: "AWAY @ HOME"  e.g. "ORL @ PHI"
    """
    date_str = target_date.strftime("%Y-%m-%d")
    board = scoreboardv3.ScoreboardV3(game_date=date_str, league_id="00")
    df = board.game_header.get_data_frame()

    matchup_map = {}
    for _, row in df.iterrows():
        game_id = str(row["gameId"])
        away = _extract_tricode(row, "away")
        home = _extract_tricode(row, "home")
        matchup_map[game_id] = f"{away} @ {home}"

    return matchup_map
