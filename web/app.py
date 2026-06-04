"""
web/app.py
──────────
Flask web application. Serves the leaderboard UI and a JSON API.

Local development:
    python -m web.app

Production (Railway):
    gunicorn web.app:app
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo
import os
import threading
from flask import Flask, jsonify, render_template, abort, request
from flask_caching import Cache

from config.roster import ROSTER
from config.settings import LEAGUE_START, LEAGUE_END, ROTO_CATEGORIES, SECRET_KEY, ACTIVE_TEAMS, ADMIN_TOKEN
from db.queries import (
    get_season_standings,
    get_season_stat_totals,
    get_season_owner_game_logs,
    get_season_owner_player_totals,
    get_last_updated,
    get_trends,
    get_season_stat_leaders,
)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["JSON_SORT_KEYS"] = False

# ── One-time database initialisation ─────────────────────────────────────────
# Set INIT_DB=1 in environment variables to run schema creation on startup.
# Remove the variable after the first successful deploy.
import os
if os.environ.get("INIT_DB") == "1":
    from db.schema import init_db, migrate_db
    init_db()
    migrate_db()

# ── Cache configuration ───────────────────────────────────────────────────────
# SimpleCache works for a single-process server (local dev + single Railway dyno).
# Upgrade to RedisCache if multiple dynos are ever needed.
app.config["CACHE_TYPE"]              = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"]   = 300   # 5 minutes

cache = Cache(app)

_VALID_OWNERS = {p["Fantasy_Owner"] for p in ROSTER}


# ── Cached data helpers ───────────────────────────────────────────────────────

@cache.cached(timeout=300, key_prefix="season_standings")
def _get_standings_cached():
    """Compute and cache the full standings for up to 5 minutes."""
    standings = get_season_standings()
    for row in standings:
        row["total_score"] = round(row["total_score"], 1)
        row["fg_pct"]      = round(row.get("fg_pct", 0) * 100, 1)
        row["ft_pct"]      = round(row.get("ft_pct", 0) * 100, 1)
        for col, _, _ in ROTO_CATEGORIES:
            rank_key = f"{col}_rank"
            if rank_key in row:
                row[rank_key] = round(row[rank_key], 1)
    trends = get_trends()
    for row in standings:
        row["trend"] = trends.get(row["fantasy_owner"], "new")
    return standings


# ── Template helpers ──────────────────────────────────────────────────────────

def _days_remaining() -> int:
    end = datetime.strptime(LEAGUE_END, "%Y-%m-%d").date()
    return max(0, (end - date.today()).days)


def _days_elapsed() -> int:
    start = datetime.strptime(LEAGUE_START, "%Y-%m-%d").date()
    return max(0, (date.today() - start).days)


def _common_ctx() -> dict:
    return {
        "league_start":   LEAGUE_START,
        "league_end":     LEAGUE_END,
        "days_remaining": _days_remaining(),
        "days_elapsed":   _days_elapsed(),
    }


def _today_fields() -> dict:
    today = date.today()
    return {
        "as_of":         str(today),
        "today_display": today.strftime("%b %d, %Y").replace(" 0", " "),
        "last_updated":  get_last_updated(),
        "server_time":   datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%I:%M %p").lstrip("0"),
            }


# ── HTML routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    full_labels = {
        "PTS":    "Points",
        "FG_PCT": "Field Goal %",
        "FT_PCT": "Free Throw %",
        "FG3M":   "3-Pointers Made",
        "REB":    "Rebounds",
        "AST":    "Assists",
        "STL":    "Steals",
        "BLK":    "Blocks",
        "TO":     "Turnovers",
    }
    categories = [
        {"col": col, "label": label, "full_label": full_labels.get(col, label)}
        for col, label, _ in ROTO_CATEGORIES
    ]
    return render_template("index.html", categories=categories, **_common_ctx())


@app.route("/owner/<owner_name>")
def owner_page(owner_name):
    if owner_name not in _VALID_OWNERS:
        abort(404)

    standings = _get_standings_cached()
    owner_row = next((r for r in standings if r["fantasy_owner"] == owner_name), None)
    place     = owner_row["place"]       if owner_row else "—"
    score     = owner_row["total_score"] if owner_row else "—"

    ordinals  = {1: "1st", 2: "2nd", 3: "3rd"}
    place_str = ordinals.get(place, f"{place}th") if isinstance(place, int) else place

    return render_template(
        "owner.html",
        owner=owner_name,
        place_str=place_str,
        score=score,
        **_common_ctx()
    )


# ── JSON API routes ───────────────────────────────────────────────────────────

@app.route("/api/standings")
def api_standings():
    return jsonify({
        **_today_fields(),
        "league_start": LEAGUE_START,
        "league_end":   LEAGUE_END,
        "standings":    _get_standings_cached(),
    })


@app.route("/leaders")
def leaders_page():
    return render_template("leaders.html", **_common_ctx())


@app.route("/api/leaders")
def api_leaders():
    leaders_dict = get_season_stat_leaders()
    # Return as a list of {category, players} objects rather than a dict
    # so Flask's JSON serialiser cannot reorder the keys alphabetically.
    leaders_list = [
        {"category": cat, "players": players}
        for cat, players in leaders_dict.items()
    ]
    return jsonify({
        **_today_fields(),
        "leaders": leaders_list,
    })
    totals = get_season_stat_totals()
    for row in totals:
        row["fg_pct"] = round(row.get("fg_pct", 0) * 100, 1)
        row["ft_pct"] = round(row.get("ft_pct", 0) * 100, 1)
    return jsonify(totals)


@app.route("/api/owner/<owner_name>")
def api_owner(owner_name):
    if owner_name not in _VALID_OWNERS:
        abort(404)

    cache_key = f"owner_{owner_name}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    totals = get_season_owner_player_totals(owner_name)
    logs   = get_season_owner_game_logs(owner_name)

    for row in totals + logs:
        for pct in ("fg_pct", "fg3_pct", "ft_pct"):
            if pct in row:
                row[pct] = round(row[pct] * 100, 1)

    response = jsonify({
        **_today_fields(),
        "owner":         owner_name,
        "league_start":  LEAGUE_START,
        "league_end":    LEAGUE_END,
        "active_teams":  list(ACTIVE_TEAMS),
        "player_totals": totals,
        "game_logs":     logs,
    })
    cache.set(cache_key, response, timeout=300)
    return response


# ── Cache invalidation — called from main.py after pipeline runs ──────────────

def clear_cache():
    """Explicitly clear all cached data. Call after main.py writes new data."""
    with app.app_context():
        cache.clear()
    print("   🗑️   Flask cache cleared.")


# ── Admin pipeline page ───────────────────────────────────────────────────────

# Tracks the current pipeline run state so the admin page can poll for status.
_pipeline_state = {"running": False, "last_run": None, "last_result": None}
_pipeline_lock  = threading.Lock()


def _run_pipeline(target_date_str: str):
    """Run the pipeline in a background thread."""
    from nba.boxscore import build_game_logs
    from db.store import save_game_logs, save_standings_snapshot
    from db.queries import get_season_standings
    from datetime import datetime as dt

    with _pipeline_lock:
        _pipeline_state["running"] = True
        _pipeline_state["last_result"] = None
        _pipeline_state["last_run"] = None

    try:
        target_date = dt.strptime(target_date_str, "%Y-%m-%d").date()
        df = build_game_logs(target_date)

        if df.empty:
            result = f"No games found for {target_date_str}."
        else:
            standings = get_season_standings()
            save_standings_snapshot(standings, target_date)
            for gid in df["GAME_ID"].unique():
                save_game_logs(df[df["GAME_ID"] == gid], target_date, str(gid))
            cache.clear()
            n_players = len(df)
            n_owners  = df["Fantasy_Owner"].nunique()
            result = f"✅ Saved {n_players} player log(s) across {n_owners} owner(s) for {target_date_str}."

    except Exception as exc:
        result = f"❌ Error: {exc}"

    with _pipeline_lock:
        _pipeline_state["running"]   = False
        _pipeline_state["last_run"]  = target_date_str
        _pipeline_state["last_result"] = result


@app.route("/admin")
def admin_page():
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN:
        abort(404)
    return render_template("admin.html", token=token,
                           league_start=LEAGUE_START, league_end=LEAGUE_END,
                           today=str(date.today()))


@app.route("/api/admin/run", methods=["POST"])
def api_admin_run():
    token = request.json.get("token", "")
    if token != ADMIN_TOKEN:
        abort(404)

    if _pipeline_state["running"]:
        return jsonify({"status": "running", "message": "Pipeline already running."})

    target_date = request.json.get("date", str(date.today()))
    thread = threading.Thread(target=_run_pipeline, args=(target_date,), daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": f"Pipeline started for {target_date}."})


@app.route("/api/admin/status")
def api_admin_status():
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN:
        abort(404)
    return jsonify(_pipeline_state)


# ── Dev server ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
