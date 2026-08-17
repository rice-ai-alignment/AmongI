# among-i dashboard

Vue 3 + Firestore web app for running and observing Among-I experiments. Terminal-styled UI (ASCII tables, typewriter text) with these tabs:

- **experiments** — studies/experiments, config editor (tree/JSON/validate), data viewer, game inspector, run button
- **jobs** — active + history job tables; click a job for a full status popup with per-trial breakdown
- **servers** — live server heartbeats
- **admin** — user permission management (admins only)
- **documentation** — in-app docs

## Setup

```bash
npm install
cp firebase-config.example.js public/firebase-config.js   # edit to match your Firebase project
npm run dev                                               # http://localhost:5173
```

`public/firebase-config.js` is gitignored — it defines `FIREBASE_CONFIG` (apiKey/projectId/etc.), which `index.html` uses to initialize Firebase before the app loads.

## Build & Deploy

```bash
npm run build                        # outputs dist/
firebase deploy --only hosting       # serves dist/ (see firebase.json)
firebase deploy --only firestore:rules   # deploy Firestore rules
firebase deploy --only storage           # deploy storage.rules
```

## The shared config compiler

The config validator lives in `engine/schema_compiler.js` (pure JS, single source of truth). The `predev`/`prebuild` hooks run `export-schema.sh`, which:

1. Exports `schema.json` from the Python component registry (`engine/components/__init__.py` via `engine/experiment.py export_schema()`)
2. Copies `schema.json` + `schema_compiler.js` into `dashboard/public/`

The browser loads both natively (`window.validateConfig`); the Python pipeline calls the same JS via Node. **Never edit a copy of the compiler or the schema in this folder — they are generated.** Edit the registry in `engine/components/` or `engine/schema_compiler.js` instead.

## Firestore data model (what the app reads/writes)

- `studies/{studyId}` — name, description, owner, status
- `studies/{studyId}/experiments/{expId}` — `config`, stats (`total_games`, `by_winner`, `players`…), `trials[]`, trial metadata maps (`trial_claimed_at/by`, `trial_completed_at/by`, `trial_versions`, `trial_errors`), `cleared_at`
- `studies/{studyId}/experiments/{expId}/games/{gameId}` — game recaps; `trace/{raw}` holds the trace URL/size
- `studies/{studyId}/experiments/{expId}/archived_data/{id}` — snapshots made by clear-data (+ `games/`)
- `jobs/{jobId}` — `study_id`, `experiment_code`, `status`, timestamps, `result`
- `servers/{serverId}` — heartbeats; `users/{uid}` — permissions

All reads/writes go through `src/composables/useFirestore.js`. Config saves delete stale keys inside the stored `config` (dotted `FieldValue.delete()`) and verify with a server-forced read. Trace content is fetched from the public Firebase Storage URL stored at upload time — paths are `{study}/{exp}/{trial}/{trace,game,session}.jsonl`.

## Sample data

`public/sample_data/example_basic.json`, `example_small_kill.json`, `example_timer.json` are valid example configs (used by the reset-to-example button and the sample fallback). They are also validated by the engine's `check.sh` — update both sides when they change.
