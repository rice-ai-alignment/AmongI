# Among-I

A multi-agent LLM simulation. AI agents with distinct text-file personas explore a 2D tile world, move, chat, and play Among Us-style rounds — imposter kills, body reports, votes, ejections. Every agent decision comes from an LLM (OpenRouter). A Python engine owns all game logic, a Godot project renders it, and a Vue dashboard drives experiments, jobs, and data exploration.

## What it looks like

- **Godot renderer** — colorful Among Us-style sprites wander a tile map, chat bubbles float above them, a HUD shows the chat log.
- **Dashboard** — a terminal-styled web app with studies, a config editor (tree/JSON with validation), job queueing with per-trial status, server monitoring, game/trace inspection, and an admin panel.

## Architecture

```
┌────────────────────────┐   WebSocket :8081    ┌──────────────────────────┐
│ engine/ (Python)       │   render events      │ among-i/ (Godot)         │
│  GameEngine            │◄────────────────────►│  Server.gd (WS server)   │
│  agent.py (LLM calls)  │                      │  sprites, chat, camera   │
│  RenderClient          │                      │  (rendering only — no    │
└──────────┬─────────────┘                      │   validation or logic)   │
           │ firebase_admin                     └──────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────────┐
│ Firestore (raia-labs)                    Firebase Storage     │
│  studies/{study}/experiments/{exp}       (REST API uploads)  │
│  ├─ config, stats, trials[], trial_*     {study}/{exp}/      │
│  ├─ games/{id} + trace/{raw,summary}       {game_id}/        │
│  ├─ archived_data/{id}                      trace.jsonl     │
│  jobs/{id}, servers/{id}, users/{uid}       game.jsonl      │
│                                              session.jsonl   │
└──────────────────────────────────────────────────────────────┘
           ▲
┌──────────┴─────────────┐
│ dashboard/ (Vue 3)     │  studies · config · jobs · servers ·
└────────────────────────┘  inspect · admin · documentation
```

The loop, every ~3 seconds: engine builds context (ASCII map, nearby bots, chat, prompt, action schema) → agent calls OpenRouter → decision JSON comes back → engine applies move/attack/chat/vote → render events go to Godot.

## Repository Layout

| Directory | What's in it |
|---|---|
| `engine/` | Python game logic: `engine.py` (state machine + loop), `agent.py` (LLM agents), `server_handler.py` (jobs runner), `bridge_server.py` (Firestore/Storage pushes), `experiment.py` + `components/` (config system), `games/` (Among Us game code), `schema_compiler.js` (config validator), `personas/` |
| `among-i/` | Godot 4 project: WS server on :8081 that applies render events |
| `dashboard/` | Vue 3 web app: config editor, jobs, servers, trial inspector, admin |
| root | `docker-compose.yml` / `Dockerfile` (server deployment), `update.sh`, `.env` |

## Quick Start

### 1. Prerequisites

- Python 3.10+ (`cd engine && pip install -r requirements.txt`)
- Godot 4.x (for the renderer)
- Node 20+ (for the dashboard)
- An OpenRouter API key
- `engine/firebase-key.json` (Firebase service account — for the dashboard/server data flow)

### 2. Configure

Create `.env` in the repo root:

```bash
OPEN_ROUTER_API_KEY=sk-or-...
# MODEL=google/gemini-2.5-flash   # optional, default
# TOKEN_LIMIT=100000
# VERBOSE=1
```

### 3. Run the simulation locally

**Terminal 1 — Godot**: open `among-i/project.godot` in Godot, press F5.

**Terminal 2 — engine**:

```bash
cd engine
python run.py --config among_us_test.json --render   # with Godot
python run.py --config among_us_test.json            # headless
```

Agents load random personas from `engine/personas/`, spawn, and start playing.

### 4. Run the dashboard

```bash
cd dashboard
npm install
npm run dev        # http://localhost:5173
```

### 5. Run a jobs server

Servers poll Firestore for queued jobs and run experiments:

```bash
cd engine
python server_handler.py --name my-server
```

Or via Docker (any machine, just needs `firebase-key.json` + `docker-compose.yml`):

```bash
docker compose up -d
docker compose logs -f
```

Update a deployed server: `./update.sh` (pulls latest, bumps version, rebuilds, restarts).

## Experiments, Jobs, and Trials

- **Config** — every experiment config is a JSON tree of typed components (`Game::AmongUsGame` with `GamePhase`/`TargetedAction` entries, `AgentType`s, `WinCondition`s, expressions, conditions). The dashboard's config editor validates with the same compiler the server pipeline uses (`schema_compiler.js` against `schema.json` exported from the Python component registry). Unused parameters are hard errors.
- **Job** — a Firestore doc pointing at a study + experiment. Created by the dashboard's run button (after validating the saved config).
- **Trial** — one individual game. The experiment doc holds a `trials[]` status array; each server claims a random pending index via a Firestore transaction, waits 0–5s to mitigate collisions, and runs one game. Completion metadata records which server, when, and which version ran each trial.
- **Data & storage** — finished-game recaps and stats go to Firestore; raw per-trial logs and the decision trace go to Firebase Storage at `{study}/{experiment}/{trial}/` (`trace.jsonl`, `game.jsonl`, `session.jsonl`), publicly readable for the dashboard.
- **Clear data** — archives stats, games, and trial metadata under `archived_data/`, resets the experiment to a fresh run-ready state, and stamps `cleared_at` so in-flight server results can't resurrect wiped data.

## Dashboard Details

- **Config tab** — tree view with tooltips and inline editing, JSON editing, and a validate tab. Locked whenever the experiment has data; unlock by clearing data. A reset-to-example button restores one of the bundled sample configs.
- **Jobs tab** — active + history tables; click any job for a popup with full status and a per-trial breakdown (claims, versions, errors).
- **Servers tab** — live heartbeat status of all registered servers.
- **Inspect tab** — pick a trial, browse its decision trace; context/decision events open in a popup.
- **Admin tab** — user permission management (admins only).

Deploying rules: `firebase deploy --only firestore:rules` and `firebase deploy --only storage` from `dashboard/`. Hosting: `firebase deploy --only hosting` (serves `dashboard/dist`).

## Log Viewer

Zero-dependency local viewer for raw engine logs:

```bash
cd engine && node server.mjs   # http://localhost:3000
```

## License

MIT. Maintained by Rice AI Alignment.
