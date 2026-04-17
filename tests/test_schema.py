"""
tests/test_schema.py
────────────────────
Tests for the _PgConnAdapter parameter translation logic in db/schema.py.

This adapter is critical infrastructure — it translates SQLite-style :param
placeholders to psycopg2-style %(param)s so all query code works identically
on both databases. These tests verify that translation is correct.
"""

import pytest
from db.schema import _PgConnAdapter


class TestParamTranslation:
    """Tests for _PgConnAdapter._translate — SQLite to psycopg2 param style."""

    def test_named_param_translated(self):
        sql, params = _PgConnAdapter._translate(
            "SELECT * FROM game_logs WHERE game_date = :today",
            {"today": "2026-04-15"}
        )
        assert "%(today)s" in sql
        assert ":today" not in sql

    def test_multiple_named_params_translated(self):
        sql, params = _PgConnAdapter._translate(
            "SELECT * FROM game_logs WHERE fantasy_owner = :owner "
            "AND game_date BETWEEN :start AND :end",
            {"owner": "Aaron", "start": "2026-04-14", "end": "2026-06-19"}
        )
        assert "%(owner)s" in sql
        assert "%(start)s" in sql
        assert "%(end)s" in sql
        assert ":owner" not in sql

    def test_none_params_returned_unchanged(self):
        sql, params = _PgConnAdapter._translate(
            "SELECT COUNT(*) FROM game_logs", None
        )
        assert params is None
        assert "game_logs" in sql

    def test_positional_params_translated(self):
        sql, params = _PgConnAdapter._translate(
            "SELECT * FROM game_logs WHERE game_date = ?",
            ["2026-04-15"]
        )
        assert "%s" in sql
        assert "?" not in sql

    def test_dict_params_returned_unchanged(self):
        params_in = {"owner": "Aaron", "start": "2026-04-14"}
        sql, params_out = _PgConnAdapter._translate(
            "SELECT * FROM game_logs WHERE fantasy_owner = :owner",
            params_in
        )
        assert params_out == params_in

    def test_underscore_in_param_name(self):
        sql, params = _PgConnAdapter._translate(
            "SELECT * FROM game_logs WHERE game_date = :game_date",
            {"game_date": "2026-04-15"}
        )
        assert "%(game_date)s" in sql
        assert ":game_date" not in sql

    def test_sql_without_params_unchanged(self):
        original = "SELECT COUNT(*) AS n FROM standings_snapshots"
        sql, params = _PgConnAdapter._translate(original, None)
        assert sql == original
