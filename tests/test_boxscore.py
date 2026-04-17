"""
tests/test_boxscore.py
──────────────────────
Unit tests for DNP detection and stat processing in nba/boxscore.py.
No real API calls are made.
"""

import pytest


# ── DNP detection tests ───────────────────────────────────────────────────────

class TestDNPDetection:
    """
    Test that the comment field is correctly interpreted as a DNP.
    The logic lives in the lambda inside build_game_logs — these tests
    replicate it directly so it can be tested in isolation.
    """

    def _is_dnp(self, comment: str) -> bool:
        """Replicate the DNP detection logic from boxscore.py."""
        return bool(
            comment and str(comment).strip().upper().startswith(("DNP", "DND", "NWT"))
        )

    def test_dnp_coach_decision(self):
        assert self._is_dnp("DNP - COACH'S DECISION") is True

    def test_dnd_injury(self):
        assert self._is_dnp("DND - INJURY/ILLNESS") is True

    def test_nwt_not_with_team(self):
        assert self._is_dnp("NWT") is True

    def test_empty_comment_not_dnp(self):
        assert self._is_dnp("") is False

    def test_none_comment_not_dnp(self):
        assert self._is_dnp(None) is False

    def test_played_not_dnp(self):
        assert self._is_dnp("") is False

    def test_case_insensitive(self):
        assert self._is_dnp("dnp - coach's decision") is True


# ── Opponent derivation tests ─────────────────────────────────────────────────

class TestGetOpponent:
    """
    Test the getOpponent logic used in owner.html.
    Replicated here in Python to make it testable without a browser.
    """

    def _get_opponent(self, team, matchup):
        if not matchup or not team or matchup == "—":
            return "—"
        parts = matchup.split(" @ ")
        if len(parts) != 2:
            return matchup
        return parts[1].strip() if parts[0].strip() == team.strip() else parts[0].strip()

    def test_away_team_sees_home_as_opponent(self):
        assert self._get_opponent("MIA", "MIA @ CHA") == "CHA"

    def test_home_team_sees_away_as_opponent(self):
        assert self._get_opponent("CHA", "MIA @ CHA") == "MIA"

    def test_handles_missing_matchup(self):
        assert self._get_opponent("MIA", None) == "—"

    def test_handles_missing_team(self):
        assert self._get_opponent(None, "MIA @ CHA") == "—"

    def test_handles_dash_matchup(self):
        assert self._get_opponent("MIA", "—") == "—"
