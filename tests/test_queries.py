"""
tests/test_queries.py
─────────────────────
Unit tests for the rotisserie ranking and standings logic in db/queries.py.
All tests use an in-memory SQLite database — no real DB or API required.
"""

import pytest
from contextlib import contextmanager
from unittest.mock import patch

from tests.helpers import insert_sample_logs


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_get_connection(conn):
    """Return a get_connection context manager that yields the given conn."""
    @contextmanager
    def _get_connection():
        yield conn
    return _get_connection


ALL_OWNERS = ["Aaron", "Brian", "Michael", "Mitch", "Reed", "Russ", "Tim"]

ROTO_CATEGORIES = [
    ("PTS",    "PTS",   False),
    ("FG_PCT", "FG%",   False),
    ("FT_PCT", "FT%",   False),
    ("FG3M",   "3PTM",  False),
    ("REB",    "REB",   False),
    ("AST",    "AST",   False),
    ("STL",    "STL",   False),
    ("BLK",    "BLK",   False),
    ("TO",     "TO",    True),
]


# ── Ranking logic tests ───────────────────────────────────────────────────────

class TestRankCategory:
    """Tests for _rank_category — the core roto scoring function."""

    def _run(self, owners_data, col, ascending=False):
        """Import and run _rank_category against a synthetic owners dict."""
        from db.queries import _rank_category
        owners = {name: dict(data) for name, data in owners_data.items()}
        _rank_category(owners, col, ascending)
        return owners

    def test_best_scorer_gets_highest_points(self):
        owners = {
            "Aaron":   {"pts": 100, "reb": 10, "ast": 5, "fg3m": 3, "to_": 2},
            "Michael": {"pts":  60, "reb":  8, "ast": 4, "fg3m": 2, "to_": 3},
            "Reed":    {"pts":  40, "reb":  6, "ast": 3, "fg3m": 1, "to_": 1},
        }
        result = self._run(owners, "PTS", ascending=False)
        assert result["Aaron"]["PTS_rank"]   == 3   # best → most points
        assert result["Michael"]["PTS_rank"] == 2
        assert result["Reed"]["PTS_rank"]    == 1   # worst → fewest points

    def test_turnovers_ascending_fewer_is_better(self):
        owners = {
            "Aaron":   {"pts": 100, "reb": 10, "ast": 5, "fg3m": 3, "to_": 1},
            "Michael": {"pts":  60, "reb":  8, "ast": 4, "fg3m": 2, "to_": 3},
            "Reed":    {"pts":  40, "reb":  6, "ast": 3, "fg3m": 1, "to_": 5},
        }
        result = self._run(owners, "TO", ascending=True)
        assert result["Aaron"]["TO_rank"]   == 3   # fewest TOs → most points
        assert result["Reed"]["TO_rank"]    == 1   # most TOs → fewest points

    def test_tied_owners_share_average_points(self):
        owners = {
            "Aaron":   {"pts": 100, "reb": 10, "ast": 5, "fg3m": 3, "to_": 2},
            "Michael": {"pts": 100, "reb":  8, "ast": 4, "fg3m": 2, "to_": 3},
            "Reed":    {"pts":  40, "reb":  6, "ast": 3, "fg3m": 1, "to_": 1},
        }
        result = self._run(owners, "PTS", ascending=False)
        # Aaron and Michael tied for 1st: share (3+2)/2 = 2.5
        assert result["Aaron"]["PTS_rank"]   == 2.5
        assert result["Michael"]["PTS_rank"] == 2.5
        assert result["Reed"]["PTS_rank"]    == 1.0

    def test_inactive_owners_get_bottom_points(self):
        """Owners with no games played should always receive the lowest points."""
        owners = {
            "Aaron":   {"pts": 100, "reb": 10, "ast": 5, "fg3m": 3, "to_": 2},
            "Brian":   {"pts":   0, "reb":  0, "ast": 0, "fg3m": 0, "to_": 0},
            "Russ":    {"pts":   0, "reb":  0, "ast": 0, "fg3m": 0, "to_": 0},
        }
        result = self._run(owners, "PTS", ascending=False)
        # Brian and Russ are inactive — share positions 1 and 2: (1+2)/2 = 1.5
        assert result["Brian"]["PTS_rank"] == 1.5
        assert result["Russ"]["PTS_rank"]  == 1.5
        assert result["Aaron"]["PTS_rank"] == 3.0   # only active owner

    def test_inactive_owners_not_rewarded_for_zero_turnovers(self):
        """Inactive owners must NOT receive the best TO rank just because they have 0 TOs."""
        owners = {
            "Aaron":   {"pts": 100, "reb": 10, "ast": 5, "fg3m": 3, "to_": 3},
            "Brian":   {"pts":   0, "reb":  0, "ast": 0, "fg3m": 0, "to_": 0},
        }
        result = self._run(owners, "TO", ascending=True)
        # Aaron is active with 3 TOs — should get more points than inactive Brian
        assert result["Aaron"]["TO_rank"] > result["Brian"]["TO_rank"]


# ── get_stat_totals tests ─────────────────────────────────────────────────────

class TestGetStatTotals:
    def test_returns_all_seven_owners(self, db_conn):
        insert_sample_logs(db_conn)
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS):
            from db.queries import get_stat_totals
            result = get_stat_totals("2026-04-01", "2026-06-30")
        assert len(result) == 7

    def test_inactive_owners_have_zero_stats(self, db_conn):
        insert_sample_logs(db_conn)
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS):
            from db.queries import get_stat_totals
            result = get_stat_totals("2026-04-01", "2026-06-30")
        inactive = [r for r in result if r["fantasy_owner"] in ("Brian", "Mitch", "Russ", "Tim")]
        for row in inactive:
            assert row["pts"] == 0
            assert row["reb"] == 0

    def test_active_owner_stats_are_summed(self, db_conn):
        insert_sample_logs(db_conn)
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS):
            from db.queries import get_stat_totals
            result = get_stat_totals("2026-04-01", "2026-06-30")
        aaron = next(r for r in result if r["fantasy_owner"] == "Aaron")
        # Aaron has two players: 30+20=50 pts, 8+6=14 reb
        assert aaron["pts"] == 50
        assert aaron["reb"] == 14


# ── get_standings tests ───────────────────────────────────────────────────────

class TestGetStandings:
    def test_first_place_has_highest_score(self, db_conn):
        insert_sample_logs(db_conn)
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS), \
             patch("db.queries.ROTO_CATEGORIES", ROTO_CATEGORIES):
            from db.queries import get_standings
            result = get_standings("2026-04-01", "2026-06-30")
        scores = [r["total_score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_place_1_is_first_row(self, db_conn):
        insert_sample_logs(db_conn)
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS), \
             patch("db.queries.ROTO_CATEGORIES", ROTO_CATEGORIES):
            from db.queries import get_standings
            result = get_standings("2026-04-01", "2026-06-30")
        assert result[0]["place"] == 1
        assert result[-1]["place"] == 7

    def test_all_owners_present(self, db_conn):
        insert_sample_logs(db_conn)
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS), \
             patch("db.queries.ROTO_CATEGORIES", ROTO_CATEGORIES):
            from db.queries import get_standings
            result = get_standings("2026-04-01", "2026-06-30")
        assert len(result) == 7
        owners_in_result = {r["fantasy_owner"] for r in result}
        assert owners_in_result == set(ALL_OWNERS)


# ── get_trends tests ──────────────────────────────────────────────────────────

class TestGetTrends:
    def _seed_snapshot(self, conn, date, placements):
        for owner, place, score in placements:
            conn.execute("""
                INSERT INTO standings_snapshots
                    (snapshot_date, fantasy_owner, place, total_score)
                VALUES (?, ?, ?, ?)
            """, (date, owner, place, score))
        conn.commit()

    def test_up_when_place_improves(self, db_conn):
        insert_sample_logs(db_conn)
        self._seed_snapshot(db_conn, "2026-04-15", [
            ("Aaron", 2, 40.0), ("Michael", 1, 45.0), ("Reed", 3, 30.0),
            ("Brian", 4, 20.0), ("Mitch",   5, 15.0), ("Russ", 6, 10.0),
            ("Tim",   7,  5.0),
        ])
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS), \
             patch("db.queries.ROTO_CATEGORIES", ROTO_CATEGORIES):
            from db.queries import get_trends
            trends = get_trends()
        # Aaron is place 1 in current standings but was 2 in snapshot → up
        assert trends["Aaron"] == "up"

    def test_down_when_place_drops(self, db_conn):
        insert_sample_logs(db_conn)
        self._seed_snapshot(db_conn, "2026-04-15", [
            ("Aaron", 2, 40.0), ("Michael", 1, 45.0), ("Reed", 3, 30.0),
            ("Brian", 4, 20.0), ("Mitch",   5, 15.0), ("Russ", 6, 10.0),
            ("Tim",   7,  5.0),
        ])
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS), \
             patch("db.queries.ROTO_CATEGORIES", ROTO_CATEGORIES):
            from db.queries import get_trends
            trends = get_trends()
        # Michael was 1 in snapshot — will be lower in current standings → down
        assert trends["Michael"] == "down"

    def test_new_when_no_snapshot_exists(self, db_conn):
        insert_sample_logs(db_conn)
        with patch("db.queries.get_connection", make_get_connection(db_conn)), \
             patch("db.queries.ALL_OWNERS", ALL_OWNERS), \
             patch("db.queries.ROTO_CATEGORIES", ROTO_CATEGORIES):
            from db.queries import get_trends
            trends = get_trends()
        assert all(v == "new" for v in trends.values())
