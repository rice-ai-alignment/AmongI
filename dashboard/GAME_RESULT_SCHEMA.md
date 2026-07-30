# Game result JSON — for the stats dashboard

This is the payload shape the dashboard expects for each **finished game**. It's
a superset of the `recap` dict already built in `end_game()` in
[Scripts/Server.gd](../Scripts/Server.gd) and logged via `EventLogger.end_game(recap)`
in [Scripts/EventLogger.gd](../Scripts/EventLogger.gd) (as a `game_end` event).

## Fields

| Field | Type | Already in `recap`? | Notes |
|---|---|---|---|
| `schema_version` | string | no | Bump if you change this shape. `"1.0"` for now. |
| `session_id` | string | no (on the outer event) | e.g. `EventLogger.get_session_id()` |
| `game_id` | string | no (on the outer event) | e.g. `EventLogger.get_game_id()` |
| `started_at` | ISO 8601 string | no | Set when `set_start_game()` runs |
| `ended_at` | ISO 8601 string | no | Set when `end_game()` runs |
| `duration_sec` | number | no | `ended_at - started_at`, or just track a timer |
| `winner` | string | yes | `"crewmates"` \| `"imposters"` \| `"timeout"` |
| `kills` | number | yes | `_game_kills` |
| `ejections` | number | yes | `_game_ejections` |
| `players` | array | yes | see below |

`players[]` items — `name`/`imposter`/`alive` already exist; `color` is new but
trivial (it's just `AGENT_COLORS[client.index % AGENT_COLORS.size()]`, already
computed in `register_agent()`):

```json
{ "name": "Red", "imposter": true, "alive": false, "color": "#C51111" }
```

## How the dashboard gets this data

It polls a URL you configure in the dashboard's settings panel and expects
**either**:

1. **A clean JSON array** of objects shaped like the above (one per finished
   game) — e.g. a small endpoint at `GET /games` that reads an in-memory list
   or a `games.json` file you append to on `game_end`. This is the simplest
   option — see [sample_data/sample_games.json](sample_data/sample_games.json)
   for exactly what that response should look like.
2. **The raw `.jsonl` session log** (newline-delimited JSON) that
   `EventLogger` already writes to `res://logs/<session>.jsonl`. The dashboard
   will parse each line, keep only `type == "game_end"` events, and read the
   `recap` field off each one. If you go this route, just add the extra
   fields above into the `recap` dict before calling `EventLogger.end_game(recap)`,
   and serve that log directory over plain HTTP (e.g. `python -m http.server`
   from inside `res://logs/`, or any static file server) so the dashboard can
   fetch it with `fetch()`.

Whichever way you send it, make sure the response allows cross-origin reads
(`Access-Control-Allow-Origin: *`) if the dashboard is opened from a different
origin/port than the log server.
