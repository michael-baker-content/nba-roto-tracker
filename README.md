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

- Python 3.11 or higher
- A virtual environment manager (`venv` recommended)
- Git

---

## Local setup

### 1. Clone the repository

```powershell
# Windows PowerShell (same command on macOS / Linux)
git clone https://github.com/michael-baker-content/nba-roto-tracker.git
cd nba-roto-tracker
```

### 2. Create and activate a virtual environment

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```powershell
# Windows PowerShell (same command on macOS / Linux)
pip install -r requirements.txt
```

### 4. Configure environment variables

```powershell
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and set a `SECRET_KEY`. Leave `DATABASE_URL` blank to use the local SQLite database.

### 5. Initialise the database

```powershell
# Windows PowerShell (same command on macOS / Linux)
python -m db.schema
```

### 6. Run the daily pipeline

```powershell
# Windows PowerShell (same command on macOS / Linux)
python main.py --date YYYY-MM-DD
```

This fetches box scores for the given date, stores game logs, and saves a standings snapshot. Run it for each game day you want to backfill.

### 7. Start the web server

```powershell
# Windows PowerShell (same command on macOS / Linux)
python -m web.app
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## Adapting for your league

All league-specific configuration lives in two files.

### `config/roster.py`

Replace the `ROSTER` list with your league's players. Each entry requires:

```python
{"Fantasy_Owner": "OwnerName", "PLAYER": "Player Name", "PLAYER_ID": 1234567}
```

`PLAYER_ID` is the NBA stats player ID. You can look these up via:

```python
from nba_api.stats.static import players
results = players.find_players_by_full_name("LeBron James")
print(results)
```

Also update `OWNER_COLORS` with one hex color per owner for the Excel export.

### `config/settings.py`

Set your league's start and end dates:

```python
LEAGUE_START = "2026-04-14"
LEAGUE_END   = "2026-06-19"
```

These dates determine which game logs are included in standings calculations and how many days elapsed/remaining are shown in the header.

---

## Daily workflow

After NBA games complete each evening, run the pipeline:

```powershell
# Windows PowerShell
python main.py

# macOS / Linux (same command)
python main.py
```

This fetches today's box scores, updates the database, and saves a standings snapshot for trend tracking. The web app reflects the new data within 5 minutes (cache TTL).

To also export a file:

```powershell
# Windows PowerShell (same command on macOS / Linux)
python main.py --format xlsx   # or csv / json
```

---

## Running tests

```powershell
# Windows PowerShell (same command on macOS / Linux)
pytest tests/ -v
```

Tests use an in-memory SQLite database and mock all NBA API calls — no network access required.

---

## Project structure

```
nba-roto-tracker/
│
├── main.py                  # Daily pipeline entry point
├── requirements.txt
├── runtime.txt              # Python version for hosted platforms
├── Procfile                 # gunicorn entry point for hosted deployment
├── .env.example
├── .gitignore
│
├── config/
│   ├── roster.py            # ← Edit this for your league (players + owners)
│   └── settings.py          # ← Edit this for your league (dates, categories)
│
├── nba/
│   ├── scoreboard.py        # Fetches game IDs and matchup strings
│   └── boxscore.py          # Fetches and processes box scores
│
├── db/
│   ├── schema.py            # Table definitions and migrations
│   ├── store.py             # Writes data to the database
│   └── queries.py           # Reads standings, trends, and game logs
│
├── output/                  # Optional file export writers
│   ├── excel_writer.py
│   ├── csv_writer.py
│   └── json_writer.py
│
├── web/
│   ├── app.py               # Flask application
│   ├── static/
│   │   ├── style.css
│   │   ├── ad_banner.svg
│   │   └── ad_rectangle.svg
│   └── templates/
│       ├── index.html       # Leaderboard
│       └── owner.html       # Team roster page
│
└── tests/
    ├── conftest.py          # Shared fixtures
    ├── test_queries.py      # Rotisserie ranking logic
    ├── test_scoreboard.py   # Matchup string parsing
    ├── test_boxscore.py     # DNP detection
    └── test_web.py          # Flask route integration
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | No | PostgreSQL connection URL. If absent, uses local `fantasy.db` (SQLite). |
| `TZ` | No | Timezone for the server. Set to `America/Los_Angeles` (or your timezone) to ensure correct date handling. |
| `LEAGUE_START` | No | Overrides the default in `settings.py`. Format: `YYYY-MM-DD`. |
| `LEAGUE_END` | No | Overrides the default in `settings.py`. Format: `YYYY-MM-DD`. |
| `INIT_DB` | No | Set to `1` on first deploy to auto-create database tables on startup. Remove after the first successful deployment. |

---

## Deploying to a live server

The project is designed to run on any platform that supports Python web applications. The key requirements are:

- A process that runs `gunicorn web.app:app` continuously (the web server)
- A scheduled job that runs `python main.py` once per day after games complete (the pipeline)
- A PostgreSQL database (SQLite is not suitable for hosted environments)
- The ability to set environment variables

### Push to GitHub

```powershell
# Windows PowerShell (same commands on macOS / Linux)
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/nba-roto-tracker.git
git push -u origin main
```

### Recommended platforms

**Railway** ([railway.app](https://railway.app)) — connect your GitHub repo and add a PostgreSQL database plugin. Railway sets `DATABASE_URL` automatically. Note the following Railway-specific steps:

- Add a `runtime.txt` file to your repo containing `python-3.11` so Railway detects the correct Python version
- In your service settings, set the **Start Command** explicitly to `python -m gunicorn web.app:app` — Railway's auto-detection may not find gunicorn in the virtualenv path
- Make sure `gunicorn` is listed in `requirements.txt`
- For the daily pipeline, add a second **Cron Job** service pointing to the same repo with start command `python main.py` and schedule `0 9 * * *` (9 AM UTC / 1 AM PT — after west coast games finish). Note that Railway's cloud IPs may be rate-limited by the NBA API — running the pipeline manually from a local machine is more reliable

**Render** ([render.com](https://render.com)) — create a Web Service from your repo and a separate Cron Job service. Managed PostgreSQL available as an add-on.

**Heroku** ([heroku.com](https://heroku.com)) — use the `Heroku Postgres` add-on and the `Heroku Scheduler` add-on for the daily pipeline. No free tier.

**VPS (DigitalOcean, Linode, etc.)** — run gunicorn behind nginx, use PostgreSQL installed on the server, and schedule `main.py` with a system cron job.

### What every deployment needs

**1. Set environment variables**

Set `SECRET_KEY`, `DATABASE_URL`, and `TZ` in your platform's environment settings. See the [Environment variables](#environment-variables) table above for details.

**2. Initialise the database**

If your platform provides a shell, run:

```powershell
# Windows PowerShell (same command on macOS / Linux)
python -m db.schema
```

If no shell is available (e.g. Railway free tier), add `INIT_DB=1` as an environment variable before your first deploy. The app will create the tables automatically on startup. Remove this variable after the first successful deployment.

**3. Backfill historical data**

Run the pipeline from your local machine with `DATABASE_URL` pointed at your production database. You will need `psycopg2-binary` installed locally:

```powershell
# Windows PowerShell (same command on macOS / Linux)
pip install psycopg2-binary
```

Then set `DATABASE_URL` and run the pipeline for each game day:

```powershell
# Windows PowerShell
$env:DATABASE_URL="postgresql://..."
python main.py --date YYYY-MM-DD   # repeat for each game day
Remove-Item Env:DATABASE_URL

# macOS / Linux
export DATABASE_URL="postgresql://..."
python main.py --date YYYY-MM-DD   # repeat for each game day
unset DATABASE_URL
```

**4. Schedule the daily pipeline**

The pipeline should run once per day after NBA games typically finish. For US leagues, `0 9 * * *` (9 AM UTC / 1 AM PT) is recommended — this gives enough time for late west coast games to finish and for final box scores to be available on the NBA API.

If running manually from a local machine each night, the commands are:

```powershell
# Windows PowerShell
$env:DATABASE_URL="postgresql://..."
python main.py
Remove-Item Env:DATABASE_URL

# macOS / Linux
export DATABASE_URL="postgresql://..."
python main.py
unset DATABASE_URL
```

### A note on the NBA API

The nba_api library makes requests to NBA.com, which rate-limits by IP address. Cloud server IPs are more likely to be throttled than residential IPs. The pipeline includes a 0.6-second delay between box score requests. If you encounter frequent failures, increasing this delay in `nba/boxscore.py` (`fetch_box_score`'s `delay` parameter) is the recommended fix.

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
