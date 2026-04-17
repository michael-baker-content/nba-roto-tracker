"""
tests/test_web.py
─────────────────
Integration tests for the Flask routes in web/app.py.
All database and external calls are mocked — no real DB or API needed.
"""

import pytest
from unittest.mock import patch, MagicMock


MOCK_STANDINGS = [
    {
        "fantasy_owner": "Aaron",   "place": 1, "total_score": 48.5,
        "fg_pct": 47.2, "ft_pct": 82.1, "fg3m": 12,
        "pts": 320, "reb": 80, "ast": 45, "stl": 15, "blk": 8, "to_": 30,
        "trend": "up",
        "PTS_rank": 7, "FG_PCT_rank": 6, "FT_PCT_rank": 5, "FG3M_rank": 7,
        "REB_rank": 6, "AST_rank": 5, "STL_rank": 6, "BLK_rank": 5, "TO_rank": 7,
    },
]

MOCK_TOTALS = [{"player_name": "Player A", "team": "OKC", "games_played": 2,
                "pts": 50, "fg_pct": 0.47, "ft_pct": 0.82, "fg3_pct": 0.38,
                "fgm": 18, "fga": 38, "fg3m": 5, "fg3a": 13,
                "ftm": 9, "fta": 11, "oreb": 2, "dreb": 8, "reb": 10,
                "ast": 6, "stl": 2, "blk": 1, "to_": 4}]

MOCK_LOGS = [{"game_date": "2026-04-15", "player_name": "Player A",
              "team": "OKC", "matchup": "MIA @ CHA", "dnp": 0,
              "pts": 25, "fg_pct": 0.48, "ft_pct": 0.80, "fg3_pct": 0.40,
              "fgm": 9, "fga": 19, "fg3m": 2, "fg3a": 5,
              "ftm": 5, "fta": 6, "oreb": 1, "dreb": 5, "reb": 6,
              "ast": 3, "stl": 1, "blk": 0, "to_": 2}]


@pytest.fixture
def client():
    """Flask test client with all external dependencies mocked."""
    with patch("db.queries.get_season_standings",    return_value=MOCK_STANDINGS), \
         patch("db.queries.get_season_stat_totals",  return_value=[]), \
         patch("db.queries.get_last_updated",        return_value="Apr 15, 2026"), \
         patch("db.queries.get_games_today",         return_value=False), \
         patch("db.queries.get_trends",              return_value={"Aaron": "up"}), \
         patch("db.queries.get_season_owner_player_totals", return_value=MOCK_TOTALS), \
         patch("db.queries.get_season_owner_game_logs",     return_value=MOCK_LOGS):
        from web.app import app, cache
        app.config["TESTING"]    = True
        app.config["CACHE_TYPE"] = "NullCache"
        cache.init_app(app)
        with app.test_client() as c:
            yield c


# ── HTML route tests ──────────────────────────────────────────────────────────

class TestHTMLRoutes:
    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_contains_title(self, client):
        resp = client.get("/")
        assert b"Fantasy Basketball" in resp.data

    def test_owner_page_returns_200_for_valid_owner(self, client):
        resp = client.get("/owner/Aaron")
        assert resp.status_code == 200

    def test_owner_page_returns_404_for_invalid_owner(self, client):
        resp = client.get("/owner/NotAnOwner")
        assert resp.status_code == 404

    def test_owner_page_contains_owner_name(self, client):
        resp = client.get("/owner/Aaron")
        assert b"Aaron" in resp.data


# ── API route tests ───────────────────────────────────────────────────────────

class TestAPIRoutes:
    def test_standings_returns_200(self, client):
        resp = client.get("/api/standings")
        assert resp.status_code == 200

    def test_standings_response_has_required_keys(self, client):
        data = client.get("/api/standings").get_json()
        for key in ("standings", "as_of", "today_display", "last_updated",
                    "server_time", "games_today"):
            assert key in data, f"Missing key: {key}"

    def test_standings_contains_owners(self, client):
        data = client.get("/api/standings").get_json()
        assert len(data["standings"]) > 0
        assert data["standings"][0]["fantasy_owner"] == "Aaron"

    def test_standings_trend_field_present(self, client):
        data = client.get("/api/standings").get_json()
        assert "trend" in data["standings"][0]

    def test_owner_api_returns_200(self, client):
        resp = client.get("/api/owner/Aaron")
        assert resp.status_code == 200

    def test_owner_api_returns_404_for_invalid(self, client):
        resp = client.get("/api/owner/NotAnOwner")
        assert resp.status_code == 404

    def test_owner_api_has_required_keys(self, client):
        data = client.get("/api/owner/Aaron").get_json()
        for key in ("owner", "player_totals", "game_logs",
                    "today_display", "last_updated", "games_today"):
            assert key in data, f"Missing key: {key}"

    def test_owner_api_player_totals_have_stat_fields(self, client):
        data = client.get("/api/owner/Aaron").get_json()
        totals = data["player_totals"]
        assert len(totals) > 0
        row = totals[0]
        for field in ("player_name", "team", "games_played", "pts",
                      "fg_pct", "reb", "ast"):
            assert field in row, f"Missing field: {field}"
