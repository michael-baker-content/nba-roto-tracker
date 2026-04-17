"""
config/settings.py
──────────────────
Central configuration for the league. Reads from environment variables
when present (production), falls back to sensible local defaults.

To adapt this project for your league, you need to change two things here:
    1. LEAGUE_START and LEAGUE_END — the dates your playoff season runs.
    2. ROTO_CATEGORIES — the statistical categories your league scores.

All other settings (database, Flask secret) are handled via environment
variables. See .env.example for details.
"""

import os
from pathlib import Path

# ── Database ──────────────────────────────────────────────────────────────────
# On a hosted platform, DATABASE_URL is typically injected automatically when
# you add a PostgreSQL plugin. Locally, we fall back to a SQLite file in the
# project root — no setup required.
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).resolve().parents[1] / 'fantasy.db'}"
)

# Some platforms provide a postgres:// URL; SQLAlchemy requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ── Flask ─────────────────────────────────────────────────────────────────────
# Always set a strong SECRET_KEY in production via environment variable.
# The fallback string below is intentionally weak — fine locally, not in prod.
SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

# ── League calendar ───────────────────────────────────────────────────────────
# These dates control which game logs are included in standings calculations
# and what the header shows for "days elapsed" and "days remaining".
# Update these for your league before running the pipeline.
LEAGUE_START: str = os.environ.get("LEAGUE_START", "2026-04-14")
LEAGUE_END: str   = os.environ.get("LEAGUE_END",   "2026-06-19")

# ── Rotisserie category configuration ────────────────────────────────────────
# Each entry is a 3-tuple: (column_name, display_label, ascending)
#
#   column_name   — must match a column returned by get_stat_totals() in
#                   db/queries.py. Available columns: pts, fg_pct, ft_pct,
#                   fg3m, reb, ast, stl, blk, to_
#
#   display_label — the string shown in the leaderboard column header.
#
#   ascending     — controls ranking direction:
#                     False → higher stat value is better (most pts = rank 1)
#                     True  → lower stat value is better (fewest TOs = rank 1)
#
# To add or remove a category, add or remove a tuple from this list.
# The number of owners (7) and the scoring range (1–7) adjust automatically.
# If you change column names here, update the leaderboard JS in index.html too
# (the CAT_COLS constant mirrors this list).
ROTO_CATEGORIES = [
    ("PTS",    "PTS",   False),   # total points scored
    ("FG_PCT", "FG%",   False),   # aggregate field goal percentage
    ("FT_PCT", "FT%",   False),   # aggregate free throw percentage
    ("FG3M",   "3PTM",  False),   # three-pointers made
    ("REB",    "REB",   False),   # total rebounds
    ("AST",    "AST",   False),   # total assists
    ("STL",    "STL",   False),   # total steals
    ("BLK",    "BLK",   False),   # total blocks
    ("TO",     "TO",    True),    # turnovers — fewer is better
]
