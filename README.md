# Geopolitics UCT Exam

A Flask application for a turn-based, Risk-style geopolitics strategy game. One
human player faces 9 AI-controlled NPC nations across a 10-country board.
MongoDB Atlas is used for persistence.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `MONGO_URI` (and optionally
   `MONGO_DB_NAME`, `SECRET_KEY`, `GEMINI_API_KEY`, `PORT`).
4. Start the app with `python run.py` and open `http://127.0.0.1:5000`.

Authentication is username/password with server-side session cookies (no JWT
or bearer tokens are used). Signup and login are at `/api/auth/signup` and
`/api/auth/login`. Game-state-changing routes require a logged-in session;
`GET /api/games/<game_id>` is public so a shared game link works in read-only
spectator mode for visitors who aren't the game's owner.

## Country data

Run `python -m database.seed_countries` after configuring MongoDB, or just
start the app — `run.py` seeds the `countries` collection automatically on
startup if it's empty, using the built-in sample dataset in
`database/seed_countries.py` (`WORLD_COUNTRIES_SEED`).

## Environment

See `.env.example` for supported settings. AI battle commentary uses the
Google Gemini API when `GEMINI_API_KEY` is set; otherwise the service falls
back to locally generated commentary with no external call.

## API overview

- `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- `GET /api/countries?search=...&min_tier=...`
- `GET /api/games?status=...&search=...&mine=true|false`
- `POST /api/games/new` with `{ "country_name": "..." }` — starts a new game: the chosen
  country plus 9 randomly selected NPC countries, random turn order
- `GET /api/games/<game_id>` — public; includes `can_play` (true only for the game's owner)
- `GET /api/analytics` — platform-wide totals and top commanders by win count
- `POST /api/games/<game_id>/reinforce` with `{ "country_name": "...", "amount": n }`
- `POST /api/games/<game_id>/transfer` with `{ "from_country": "...", "to_country": "...", "amount": n }`
  (source country must keep at least 1 soldier)
- `POST /api/games/<game_id>/attack-roll` with `{ "attacker_country": "...", "defender_country": "..." }`
  — one dice-rolling phase; call again on the same pair to keep rolling, one attack target per turn
- `POST /api/games/<game_id>/stop-attack`, `POST /api/games/<game_id>/end-turn`
- `POST /api/games/<game_id>/simulate-npc` — runs the current NPC's full turn
  (reinforce → transfer → heuristic attack → commentary)

`run.py` is the single source of truth for routes — if anything above looks
out of date, that file wins.
