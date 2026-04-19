# nba-roto-tracker

A self-hosted fantasy basketball playoff tracker with a live leaderboard, per-team roster pages, and rotisserie standings. Built with Python, Flask, and SQLite (PostgreSQL in production).

**Live demo:** [web-production-36aa6.up.railway.app](https://web-production-36aa6.up.railway.app/)

---

## Overview

This project fetches NBA box score data once per day using the [nba_api](https://github.com/swar/nba_api) library, stores game logs for a set of drafted players, computes rotisserie standings across nine statistical categories, and serves a responsive web app with dark mode support.

**Rotisserie categories:** PTS · FG% · FT% · 3PTM · REB · AST · STL · BLK · TO

Each owner is ranked 1 through n per category (n = best, 1 = worst; TO is inverted). Total score is the sum of all category ranks. Trend indicators show movement since the last game day.

---

## Prerequisites

- Python 3.11+
- Git

---

## Local setup

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env       # then set SECRET_KEY in .env
python -m db.schema
python main.py --date YYYY-MM-DD  # backfill each game day
python -m web.app                 # http://localhost:5000
```

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then set SECRET_KEY in .env
python -m db.schema
python main.py --date YYYY-MM-DD  # backfill each game day
python -m web.app                 # http://localhost:5000
```

---

## Adapting for your league

All league-specific configuration lives in two files.

### `config/roster.py`

Replace the `ROSTER` list with your league's players:

```python
{"Fantasy_Owner": "OwnerName", "PLAYER": "Player Name", "PLAYER_ID": 1234567}
```

Look up `PLAYER_ID` values via the NBA stats API:

```python
from nba_api.stats.static import players
players.find_players_by_full_name("LeBron James")
```

Also update `OWNER_COLORS` with one hex color per owner for the Excel export.

### `config/settings.py`

Set your league's start and end dates:

```python
LEAGUE_START = "2026-04-14"
LEAGUE_END   = "2026-06-19"
```

---

## Daily workflow

Run after games complete each evening:

```powershell
# Windows PowerShell
$env:DATABASE_URL="postgresql://..."   # omit this line when running against local SQLite
python main.py
Remove-Item Env:DATABASE_URL
```

```bash
# macOS / Linux
export DATABASE_URL="postgresql://..."  # omit when running against local SQLite
python main.py
unset DATABASE_URL
```

The snapshot is saved before game logs are written, so trend arrows on the leaderboard reflect the current run's movement immediately. The web app cache refreshes within 5 minutes.

---

## Running tests

```bash
pytest tests/ -v
```

Tests use an in-memory SQLite database and mock all NBA API calls — no network access required.

---

## Project structure

```
nba-roto-tracker/
├── main.py                  # Daily pipeline entry point
├── requirements.txt
├── runtime.txt              # Python version for hosted platforms
├── Procfile                 # gunicorn entry point
├── config/
│   ├── roster.py            # ← Edit this for your league (players + owners)
│   └── settings.py          # ← Edit this for your league (dates, categories)
├── nba/
│   ├── scoreboard.py        # Fetches game IDs and matchup strings
│   └── boxscore.py          # Fetches and processes box scores
├── db/
│   ├── schema.py            # Table definitions, migrations, and DB adapter
│   ├── store.py             # Writes data to the database
│   └── queries.py           # Reads standings, trends, and game logs
├── output/                  # Optional file export writers (xlsx, csv, json)
├── web/
│   ├── app.py               # Flask application
│   ├── static/              # CSS and SVG assets
│   └── templates/           # index.html (leaderboard), owner.html (team page)
└── tests/                   # pytest suite (55 tests)
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | No | PostgreSQL connection URL. If absent, uses local `fantasy.db` (SQLite). |
| `TZ` | No | Server timezone, e.g. `America/Los_Angeles`. Ensures correct date handling. |
| `LEAGUE_START` | No | Overrides the default in `settings.py`. Format: `YYYY-MM-DD`. |
| `LEAGUE_END` | No | Overrides the default in `settings.py`. Format: `YYYY-MM-DD`. |
| `INIT_DB` | No | Set to `1` on first deploy to auto-create tables on startup. Remove after first successful deployment. |

---

## Deploying to a live server

Requires a platform that supports Python web apps, PostgreSQL, and environment variables. The web process runs `gunicorn web.app:app` (defined in `Procfile`).

### Environment setup

Set `SECRET_KEY`, `DATABASE_URL`, and `TZ` on your platform. Most platforms that offer a managed PostgreSQL add-on will inject `DATABASE_URL` automatically.

### Database initialisation

If your platform provides a shell, run `python -m db.schema` once after provisioning the database. If not, set `INIT_DB=1` as an environment variable before your first deploy — the app will create the tables on startup. Remove the variable after the first successful deployment.

### Backfilling from a local machine

Install `psycopg2-binary` locally, then point `DATABASE_URL` at your production database and run the pipeline for each past game day:

```powershell
# Windows PowerShell
$env:DATABASE_URL="postgresql://..."
python main.py --date YYYY-MM-DD
Remove-Item Env:DATABASE_URL
```

```bash
# macOS / Linux
export DATABASE_URL="postgresql://..."
python main.py --date YYYY-MM-DD
unset DATABASE_URL
```

### Scheduling the daily pipeline

The pipeline needs to run once per day after games complete. A cron expression of `0 9 * * *` (9 AM UTC / 1 AM PT) covers most US game nights. The command is `python main.py`.

Note that cloud platform IPs are often rate-limited by the NBA API, which can cause the scheduled job to time out. Running the pipeline manually from a local machine each night is a reliable alternative — it takes only a few seconds.

### Railway-specific notes

- Add a `runtime.txt` file containing `python-3.11` for correct Python version detection
- Set the service **Start Command** explicitly to `python -m gunicorn web.app:app` — auto-detection may not find gunicorn in the virtualenv
- Ensure `gunicorn` is in `requirements.txt`
- Railway's PostgreSQL plugin sets `DATABASE_URL` automatically via a `${{Postgres.DATABASE_URL}}` variable reference

---

## Tech stack

| Layer | Technology |
|---|---|
| Data pipeline | Python · nba_api · pandas |
| Database | SQLite (local) · PostgreSQL (production) |
| Web framework | Flask · flask-caching |
| Frontend | Vanilla HTML/CSS/JS (no build step) |
| Deployment | gunicorn · any WSGI-compatible host |
| Testing | pytest |

---

## License

MIT
