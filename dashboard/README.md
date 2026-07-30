# among-i match stats dashboard

A static, single-page dashboard that polls a URL for finished-game JSON and
tabulates crewmate/impostor win rates, per-player stats, and a match log. No
build step, no dependencies — just `index.html` + `styles.css` + `app.js`.

## Run it

Browsers block `fetch()` over `file://`, so serve the folder instead of
double-clicking `index.html`:

```bash
python3 -m http.server 4173 --directory dashboard
```

Then open `http://localhost:4173`.

## Using it

1. Click **load sample** to see it populated with fake data
   (`sample_data/sample_games.json`) — good for checking the layout before a
   real server exists.
2. Paste the URL into **endpoint** and click **ping now**, or just let it auto-poll (the interval dropdown).
3. Results are deduped by `session_id` + `game_id` and kept in the browser's
   `localStorage`, so history survives reloads even if the server only ever
   returns the latest game.
4. **clear** wipes locally stored history (does not touch the server).

See [GAME_RESULT_SCHEMA.md](GAME_RESULT_SCHEMA.md) for the exact JSON shape
the dashboard expects.
