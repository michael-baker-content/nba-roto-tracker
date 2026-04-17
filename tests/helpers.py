"""
tests/helpers.py
────────────────
Shared utility functions for seeding test data.
Import directly: from tests.helpers import insert_sample_logs
"""

SAMPLE_LOGS = [
    # owner, player_id, player_name, team, matchup, pts, reb, ast, to_
    ("Aaron",   1, "Player A1", "OKC", "MIA @ CHA", 30, 8, 5, 3),
    ("Aaron",   2, "Player A2", "OKC", "MIA @ CHA", 20, 6, 4, 2),
    ("Michael", 3, "Player M1", "BOS", "ORL @ PHI", 25, 7, 6, 4),
    ("Reed",    4, "Player R1", "GSW", "GSW @ LAC", 15, 4, 3, 1),
]


def insert_sample_logs(conn, game_date="2026-04-15", game_id="0052500101"):
    """Seed a test database connection with representative game log rows."""
    for owner, pid, name, team, matchup, pts, reb, ast, to_ in SAMPLE_LOGS:
        conn.execute("""
            INSERT INTO game_logs
                (game_date, game_id, fantasy_owner, player_id, player_name,
                 team, matchup, pts, reb, ast, to_)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (game_date, game_id, owner, pid, name, team, matchup, pts, reb, ast, to_))
    conn.commit()
