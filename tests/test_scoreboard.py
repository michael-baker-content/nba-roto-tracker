"""
tests/test_scoreboard.py
────────────────────────
Unit tests for the NBA scoreboard helpers in nba/scoreboard.py.
No real API calls are made — all tests mock the nba_api response.
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from nba.scoreboard import _extract_tricode, get_matchup_map


# ── _extract_tricode tests ────────────────────────────────────────────────────

class TestExtractTricode:
    def _row(self, game_code):
        return pd.Series({"gameCode": game_code, "gameId": "0052500101"})

    def test_extracts_away_team(self):
        row = self._row("20260414/MIACHA")
        assert _extract_tricode(row, "away") == "MIA"

    def test_extracts_home_team(self):
        row = self._row("20260414/MIACHA")
        assert _extract_tricode(row, "home") == "CHA"

    def test_extracts_three_char_codes(self):
        row = self._row("20260415/ORLPHI")
        assert _extract_tricode(row, "away") == "ORL"
        assert _extract_tricode(row, "home") == "PHI"

    def test_returns_placeholder_for_missing_game_code(self):
        row = self._row("")
        assert _extract_tricode(row, "away") == "???"

    def test_returns_placeholder_for_malformed_game_code(self):
        row = self._row("20260414/AB")   # only 2 chars after slash
        assert _extract_tricode(row, "away") == "???"

    def test_handles_none_game_code(self):
        row = pd.Series({"gameCode": None, "gameId": "0052500101"})
        assert _extract_tricode(row, "away") == "???"


# ── get_matchup_map tests ─────────────────────────────────────────────────────

class TestGetMatchupMap:
    def _mock_board(self, rows):
        """Build a mock ScoreboardV3 that returns the given DataFrame rows."""
        df = pd.DataFrame(rows)
        mock_board = MagicMock()
        mock_board.game_header.get_data_frame.return_value = df
        return mock_board

    def test_builds_away_at_home_string(self):
        from datetime import date
        mock_board = self._mock_board([
            {"gameId": "0052500111", "gameCode": "20260414/MIACHA",
             "gameStatus": 3, "gameStatusText": "Final"}
        ])
        with patch("nba.scoreboard.scoreboardv3.ScoreboardV3", return_value=mock_board):
            result = get_matchup_map(date(2026, 4, 14))
        assert result["0052500111"] == "MIA @ CHA"

    def test_builds_multiple_matchups(self):
        from datetime import date
        mock_board = self._mock_board([
            {"gameId": "0052500111", "gameCode": "20260414/MIACHA",
             "gameStatus": 3, "gameStatusText": "Final"},
            {"gameId": "0052500121", "gameCode": "20260414/PORPHX",
             "gameStatus": 3, "gameStatusText": "Final"},
        ])
        with patch("nba.scoreboard.scoreboardv3.ScoreboardV3", return_value=mock_board):
            result = get_matchup_map(date(2026, 4, 14))
        assert result["0052500111"] == "MIA @ CHA"
        assert result["0052500121"] == "POR @ PHX"

    def test_placeholder_when_game_code_missing(self):
        from datetime import date
        mock_board = self._mock_board([
            {"gameId": "0052500111", "gameCode": "",
             "gameStatus": 1, "gameStatusText": "7:30 pm ET"}
        ])
        with patch("nba.scoreboard.scoreboardv3.ScoreboardV3", return_value=mock_board):
            result = get_matchup_map(date(2026, 4, 14))
        assert result["0052500111"] == "??? @ ???"
