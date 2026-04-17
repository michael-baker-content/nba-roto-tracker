# nba-roto-tracker

A self-hosted fantasy basketball playoff tracker with a live leaderboard, per-team roster pages, and rotisserie standings. Built with Python, Flask, and SQLite (PostgreSQL on Railway).

**Live demo:** [github.com/michael-baker-content](https://github.com/michael-baker-content)

---

## Overview

This project fetches NBA box score data once per day using the [nba_api](https://github.com/swar/nba_api) library, stores game logs for a set of drafted players, computes rotisserie standings across nine statistical categories, and serves a responsive web app with dark mode support.

**Rotisserie categories:** PTS · FG% · FT% · 3PTM · REB · AST · STL · BLK · TO

Each owner is ranked 1–7 per category (7 = best, 1 = worst; TO is inverted). Total score is the sum of all category ranks. Trend indicators show movement since the last game day.

---

## Prerequisites

- Python 3.11 or higher
- A virtual environment manager (`venv` recommended)
- Git

---

## Local setup

### 1. Clone the repository

```bash
git clone https://github.com/michael-baker-content/nba-roto-tracker.git
cd nba-roto-tracker
```

### 2. Create and activate a virtual environment

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set a `SECRET_KEY`. Leave `DATABASE_URL` blank to use the local SQLite database. See [Environment variables](#environment-variables) for details.

### 5. Initialise the database

```bash
python -m db.schema
```

### 6. Run the daily pipeline

```bash
python main.py --date 2026-04-15
```

This fetches box scores for the given date, stores game logs, and saves a standings snapshot. Run it for each game day you want to backfill.

### 7. Start the web server

```bash
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

Once the site is running, your daily routine is:

```bash
# After games complete each evening
python main.py
```

This fetches today's box scores, updates the database, saves a standings snapshot for trend tracking, and the web app reflects the new data within 5 minutes (cache TTL).

To also export a file:

```bash
python main.py --format xlsx   # or csv / json
```

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
│
├── main.py                  # Daily pipeline entry point
├── requirements.txt
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
| `LEAGUE_START` | No | Overrides the default in `settings.py`. Format: `YYYY-MM-DD`. |
| `LEAGUE_END` | No | Overrides the default in `settings.py`. Format: `YYYY-MM-DD`. |
| `TZ` | No | Timezone for the server. Set to `America/Los_Angeles` (or your timezone) on Railway to ensure correct date handling. |

---

## Deploying to a live server

The project is designed to run on any platform that supports Python web applications. The key requirements are:

- A process that runs `gunicorn web.app:app` continuously (the web server)
- A scheduled job that runs `python main.py` once per day after games complete (the pipeline)
- A PostgreSQL database (SQLite is not suitable for hosted environments)
- The ability to set environment variables

### Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/nba-roto-tracker.git
git push -u origin main
```

### Recommended platforms

**Railway** ([railway.app](https://railway.app)) — the simplest option. Connect your GitHub repo, add a PostgreSQL plugin, and Railway detects the `Procfile` automatically. Add a second Cron Job service pointing to the same repo with the command `python main.py` and a schedule like `0 4 * * *` (4 AM UTC). Free tier available.

**Render** ([render.com](https://render.com)) — similar to Railway. Create a Web Service from your repo and a separate Cron Job service. Managed PostgreSQL available as an add-on.

**Heroku** ([heroku.com](https://heroku.com)) — the established option with extensive documentation. Use the `Heroku Postgres` add-on and the `Heroku Scheduler` add-on for the daily pipeline. No free tier.

**VPS (DigitalOcean, Linode, etc.)** — full control. Run gunicorn behind nginx, use PostgreSQL installed on the server, and schedule `main.py` with a system cron job.

### What every deployment needs

Regardless of platform, you will need to:

**1. Set environment variables**

| Key | Value |
|---|---|
| `SECRET_KEY` | A long random string — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Your PostgreSQL connection URL (set automatically by most platforms) |
| `TZ` | Your timezone, e.g. `America/Los_Angeles` — ensures correct date handling |

**2. Initialise the database**

Run once after the platform provisions your PostgreSQL instance:

```bash
python -m db.schema
```

**3. Backfill historical data**

Run the pipeline for each game day since your league started:

```bash
python main.py --date 2026-04-14
python main.py --date 2026-04-15
# ... and so on for each game day
```

**4. Schedule the daily pipeline**

The pipeline should run once per day after NBA games typically finish. A cron expression of `0 4 * * *` (4 AM UTC) covers most game nights for US timezones. The command is simply:

```bash
python main.py
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
