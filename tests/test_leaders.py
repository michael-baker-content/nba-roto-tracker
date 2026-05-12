"""
tests/test_leaders.py
─────────────────────
Unit tests for get_stat_leaders in db/queries_leaders.py.
All tests use an in-memory SQLite database — no NBA API calls required.
"""

import pytest
from contextlib import contextmanager
from unittest.mock import patch

from tests.helpers import insert_sample_logs


def make_get_connection(conn):
    @contextmanager
    def _get_connection():
        yield conn
    return _get_connection


def insert_many_game_logs(conn, n_games=7):
    """
    Insert n_games worth of logs for a set of players so the
    games-played threshold can be tested.
    """
    players = [
        ("Aaron",   1, "Player A1", "OKC"),
        ("Michael", 2, "Player M1", "BOS"),
        ("Reed",    3, "Player R1", "GSW"),
    ]
    for game_num in range(n_games):
        game_date = f"2026-04-{14 + game_num:02d}"
        game_id   = f"005250010{game_num}"
        for owner, pid, name, team in players:
            conn.execute("""
                INSERT OR IGNORE INTO game_logs
                    (game_date, game_id, fantasy_owner, player_id, player_name,
                     team, matchup, pts, fgm, fga, fg3m, reb, ast, stl, blk, to_,
                     ftm, fta, oreb, dreb)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_date, game_id, owner, pid, name, team, "OKC @ BOS",
                  20 + game_num, 8, 15, 2, 5, 4, 1, 1, 2, 4, 5, 1, 4))
    conn.commit()


class TestGetStatLeaders:

    def test_returns_correct_category_order(self, db_conn):
        insert_sample_logs(db_conn)
        with patch("db.queries_leaders.get_connection", make_get_connection(db_conn)):
            from db.queries_leaders import get_stat_leaders
            result = get_stat_leaders("2026-04-01", "2026-06-30")

        keys = list(result.keys())
        # First category must be Points regardless of threshold state
        assert keys[0] == "Points"
        # 3-Pointers Made must come after FG% and before FT%
        assert keys.index("3-Pointers Made") > keys.index(next(k for k in keys if "Field Goal" in k))
        assert keys.index("3-Pointers Made") < keys.index(next(k for k in keys if "Free Throw" in k))
        # TO must be last
        assert "Turnover" in keys[-1]

    def test_returns_at_most_top_n_per_category(self, db_conn):
        insert_many_game_logs(db_conn, n_games=3)
        with patch("db.queries_leaders.get_connection", make_get_connection(db_conn)):
            from db.queries_leaders import get_stat_leaders
            result = get_stat_leaders("2026-04-01", "2026-06-30", top_n=2)

        for cat, players in result.items():
            assert len(players) <= 2, f"{cat} returned more than top_n=2 players"

    def test_min_gp_threshold_inactive_below_six_games(self, db_conn):
        """When max games < 6, MIN_GP=1 so all players qualify for pct categories."""
        insert_many_game_logs(db_conn, n_games=3)  # 3 games each
        with patch("db.queries_leaders.get_connection", make_get_connection(db_conn)):
            from db.queries_leaders import get_stat_leaders
            result = get_stat_leaders("2026-04-01", "2026-06-30")

        fg_key = next(k for k in result if "Field Goal" in k)
        # No threshold suffix when below 6 games
        assert ">" not in fg_key
        # All 3 players should qualify
        assert len(result[fg_key]) == 3

    def test_min_gp_threshold_active_above_six_games(self, db_conn):
        """When max games >= 6, MIN_GP=4 and label includes the qualifier."""
        insert_many_game_logs(db_conn, n_games=7)  # 7 games each
        with patch("db.queries_leaders.get_connection", make_get_connection(db_conn)):
            from db.queries_leaders import get_stat_leaders
            result = get_stat_leaders("2026-04-01", "2026-06-30")

        fg_key = next(k for k in result if "Field Goal" in k)
        assert ">4 games played" in fg_key

    def test_to_sorts_ascending(self, db_conn):
        """Turnovers category should list lowest TO totals first."""
        # Give players different TO counts
        conn = db_conn
        conn.execute("""
            INSERT INTO game_logs
                (game_date, game_id, fantasy_owner, player_id, player_name,
                 team, matchup, pts, reb, ast, to_, fgm, fga, fg3m, ftm, fta,
                 oreb, dreb, stl, blk)
            VALUES
                ('2026-04-14', 'A1', 'Aaron',   1, 'Low TO',  'OKC', 'OKC @ BOS', 10, 5, 3, 1, 4, 8, 1, 2, 3, 1, 4, 1, 0),
                ('2026-04-14', 'B1', 'Michael', 2, 'High TO', 'BOS', 'OKC @ BOS', 10, 5, 3, 8, 4, 8, 1, 2, 3, 1, 4, 1, 0)
        """)
        conn.commit()

        with patch("db.queries_leaders.get_connection", make_get_connection(db_conn)):
            from db.queries_leaders import get_stat_leaders
            result = get_stat_leaders("2026-04-01", "2026-06-30")

        to_key = next(k for k in result if "Turnover" in k)
        players = result[to_key]
        if len(players) >= 2:
            assert players[0]["value"] <= players[1]["value"]

    def test_fg_pct_uses_aggregate_not_average(self, db_conn):
        """
        FG% should be calculated from total FGM/FGA across all games,
        not by averaging per-game percentages.
        A player with 8/10 and 2/10 should show 50%, not 55% (average of 80% and 20%).
        """
        conn = db_conn
        conn.execute("""
            INSERT INTO game_logs
                (game_date, game_id, fantasy_owner, player_id, player_name,
                 team, matchup, pts, fgm, fga, fg3m, reb, ast, to_,
                 ftm, fta, oreb, dreb, stl, blk)
            VALUES
                ('2026-04-14', 'G1', 'Aaron', 1, 'Test Player', 'OKC', 'OKC @ BOS',
                 16, 8, 10, 0, 5, 3, 2, 0, 0, 1, 4, 1, 0),
                ('2026-04-15', 'G2', 'Aaron', 1, 'Test Player', 'OKC', 'OKC @ BOS',
                 4,  2, 10, 0, 5, 3, 2, 0, 0, 1, 4, 1, 0)
        """)
        conn.commit()

        with patch("db.queries_leaders.get_connection", make_get_connection(db_conn)):
            from db.queries_leaders import get_stat_leaders
            result = get_stat_leaders("2026-04-01", "2026-06-30")

        fg_key = next(k for k in result if "Field Goal" in k)
        if result[fg_key]:
            # 10 FGM / 20 FGA = 50.0%, not 55.0%
            assert result[fg_key][0]["value"] == 50.0
