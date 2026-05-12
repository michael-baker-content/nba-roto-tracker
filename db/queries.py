"""
db/queries.py
─────────────
Re-export facade. All query logic lives in focused submodules:

    queries_standings.py  — rotisserie rankings and leaderboard
    queries_owner.py      — per-owner player totals and game logs
    queries_leaders.py    — statistical leaders (top 5 per category)
    queries_meta.py       — last updated date, trends, and utility queries

Import from this module as before — nothing else in the codebase needs
to change when the underlying implementation moves between submodules.
"""

from db.queries_standings import (
    ALL_OWNERS,
    get_stat_totals,
    get_standings,
    get_season_standings,
    get_season_stat_totals,
)

from db.queries_owner import (
    get_owner_game_logs,
    get_owner_player_totals,
    get_season_owner_game_logs,
    get_season_owner_player_totals,
)

from db.queries_leaders import (
    get_stat_leaders,
    get_season_stat_leaders,
)

from db.queries_meta import (
    get_last_updated,
    get_games_today,
    get_trends,
)

__all__ = [
    "ALL_OWNERS",
    "get_stat_totals", "get_standings",
    "get_season_standings", "get_season_stat_totals",
    "get_owner_game_logs", "get_owner_player_totals",
    "get_season_owner_game_logs", "get_season_owner_player_totals",
    "get_stat_leaders", "get_season_stat_leaders",
    "get_last_updated", "get_games_today", "get_trends",
]
