"""
config/settings.py — League configuration. Edit this file for your league.

Two things to update before each season:
    1. LEAGUE_START / LEAGUE_END
    2. ACTIVE_TEAMS — remove a team's abbreviation when they are eliminated.
       Players on eliminated teams are grayed out on team pages but their
       stats still count toward season totals.
"""

import os
from pathlib import Path

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).resolve().parents[1] / 'fantasy.db'}"
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY: str  = os.environ.get("SECRET_KEY",   "dev-secret-change-in-production")
ADMIN_TOKEN: str = os.environ.get("ADMIN_TOKEN",  "dev-admin-token")

LEAGUE_START: str = os.environ.get("LEAGUE_START", "2026-04-14")
LEAGUE_END: str   = os.environ.get("LEAGUE_END",   "2026-06-19")

# Rotisserie categories: (column_name, display_label, ascending)
# ascending=True means lower is better (used for TO).
# column_name must match a column returned by get_stat_totals() in queries_standings.py.
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

ACTIVE_TEAMS: set = {
    "ATL", "BOS", "CLE", "DEN", "DET",
    "HOU", "LAL", "MIN", "NYK", "OKC", "ORL", "PHI", "SAS", "TOR",
}
