# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A World Cup 2026 prediction game ("porra") inspired by LoL Pick'em. Users predict group stage standings via drag-and-drop, then pick knockout round winners match by match. Points update in real time via WebSocket after each result is entered by the admin.

## Running the app

```bash
# Start (or rebuild after code changes)
docker compose up --build -d

# Restart only the Flask container (faster, no rebuild)
docker compose restart web

# View logs
docker compose logs -f web

# Stop
docker compose down
```

The app runs at http://localhost:5000. Admin panel at http://localhost:5000/admin (password in `.env` as `ADMIN_PASSWORD`).

The `./app` directory is bind-mounted into the container, so Python file edits take effect after `docker compose restart web` — no rebuild needed.

## Architecture

```
docker-compose.yml        # Orchestrates web + db (PostgreSQL 15)
.env                      # Credentials (never commit in real projects)
app/
  main.py                 # Flask app, all routes, SocketIO setup
  models.py               # SQLAlchemy models
  scoring.py              # Point calculation + leaderboard
  wc_data.py              # Static data: groups, teams, flags, rounds
  templates/
    base.html             # Bootstrap 5 dark, Socket.IO, toast system
    index.html            # Landing page
    join.html             # Name registration
    groups.html           # Drag-drop group predictions (SortableJS)
    bracket.html          # Knockout picks, wildcard modal
    leaderboard.html      # Live-updating rankings
    admin.html            # 5-tab admin panel
    admin_login.html
```

## Key design decisions

**Session identity**: Users are identified by a UUID stored in Flask's session cookie (`session['user_id']` → `users.id`). No login/password — just a display name. One browser session = one participant.

**Phase control**: All open/closed states live in the `app_config` DB table as string `'true'`/`'false'` values. `get_phase()` in `main.py` is the single source of truth; it also auto-closes group predictions at `GROUPS_DEADLINE` (June 11, 2026 at 18:00 UTC = 20:00 Spain CEST).

**Groups config**: The group composition is stored in `app_config` as `groups_json`. Editing `wc_data.py` alone won't update a running DB — you must also save via the admin panel's Equipos/Grupos tab or POST to `/admin/grupos-config`.

**Real-time updates**: After the admin recalculates scores, Flask-SocketIO emits `scores_updated` to all connected clients. Clients listen in `base.html` and call `window.onScoresUpdated(leaderboard)` which templates override as needed.

**Scoring**:
- Group stage: +100 pts per exact position (1st/2nd/3rd/4th) in any group
- Knockout: +200 pts per correct match winner, +300 bonus if the `final` round winner is correct
- `recalculate_all_scores()` in `scoring.py` recomputes everything from scratch (scores can go down)

**Wildcard (comodín)**: The admin awards it manually after recalculating group scores. It goes to the top group scorer. The recipient can change one locked knockout prediction. Once used, `user.wildcard_used = True`.

## Admin workflow during the tournament

1. **Before groups start**: Open `groups_open` phase → users submit predictions.
2. **After group stage ends**: Groups auto-close at deadline. Enter actual standings in "Resultados Grupos" tab → Recalculate → Award wildcard.
3. **Each knockout round**: Set up matches (team1 vs team2) in "Bracket" tab → Open the round phase → users pick → enter winner → Recalculate.

## Adding a team flag

Add an entry to `TEAM_FLAGS` in `app/wc_data.py`. The `flag()` function is registered as a Jinja2 global in `main.py` and available in all templates. Unknown teams fall back to `'🏳️'`.
