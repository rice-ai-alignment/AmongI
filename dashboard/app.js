// among-i match stats dashboard
// Polls a configurable endpoint for finished-game JSON (see GAME_RESULT_SCHEMA.md),
// accepts either a clean JSON array of game results or a raw EventLogger .jsonl log,
// and tabulates win/loss + per-player stats. All state lives in localStorage.

const STORAGE_KEYS = {
  games: "amongi_dashboard_games",
  endpoint: "amongi_dashboard_endpoint",
  interval: "amongi_dashboard_interval",
  theme: "amongi_dashboard_theme",
};

let games = [];
let pollTimer = null;

const el = (id) => document.getElementById(id);

// ---- persistence ----

function loadGames() {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.games);
    games = raw ? JSON.parse(raw) : [];
  } catch (e) {
    games = [];
  }
}

function saveGames() {
  localStorage.setItem(STORAGE_KEYS.games, JSON.stringify(games));
}

function gameKey(g) {
  return `${g.session_id || "?"}::${g.game_id || g.started_at || Math.random()}`;
}

function mergeGames(newOnes) {
  const seen = new Set(games.map(gameKey));
  let added = 0;
  for (const g of newOnes) {
    const k = gameKey(g);
    if (!seen.has(k)) {
      seen.add(k);
      games.push(g);
      added++;
    }
  }
  if (added > 0) {
    games.sort((a, b) => (a.ended_at || "").localeCompare(b.ended_at || ""));
    saveGames();
  }
  return added;
}

// ---- parsing server responses ----

// Normalizes one raw recap-ish object into the dashboard's expected shape.
function normalizeGame(raw) {
  const players = (raw.players || []).map((p) => ({
    name: p.name || "unknown",
    imposter: !!p.imposter,
    alive: !!p.alive,
    color: p.color || null,
  }));
  return {
    schema_version: raw.schema_version || "1.0",
    session_id: raw.session_id || null,
    game_id: raw.game_id || null,
    started_at: raw.started_at || null,
    ended_at: raw.ended_at || null,
    duration_sec: typeof raw.duration_sec === "number" ? raw.duration_sec : null,
    winner: raw.winner || "unknown",
    kills: typeof raw.kills === "number" ? raw.kills : 0,
    ejections: typeof raw.ejections === "number" ? raw.ejections : 0,
    players,
  };
}

// Accepts either a JSON array, or newline-delimited EventLogger events
// (filters for type === "game_end" and reads their .recap field).
function parseResponseText(text) {
  const trimmed = text.trim();
  if (trimmed.startsWith("[")) {
    const arr = JSON.parse(trimmed);
    return arr.map(normalizeGame);
  }

  // Try JSONL
  const results = [];
  for (const line of trimmed.split("\n")) {
    const l = line.trim();
    if (!l) continue;
    let obj;
    try {
      obj = JSON.parse(l);
    } catch (e) {
      continue;
    }
    if (obj.type === "game_end" && obj.recap) {
      const recap = { ...obj.recap, session_id: obj.session || obj.recap.session_id, game_id: obj.game_id || obj.recap.game_id };
      results.push(normalizeGame(recap));
    } else if (obj.winner && obj.players) {
      // a bare recap-shaped line, no envelope
      results.push(normalizeGame(obj));
    }
  }
  return results;
}

// ---- networking ----

async function pingEndpoint() {
  const url = el("endpointInput").value.trim();
  if (!url) {
    setStatus("idle", "no endpoint configured");
    return;
  }
  setStatus("pending", "pinging " + url + " ...");
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const text = await res.text();
    const parsed = parseResponseText(text);
    const added = mergeGames(parsed);
    setStatus("ok", `connected — ${parsed.length} result(s) received, ${added} new`);
    render();
  } catch (err) {
    setStatus("error", "fetch failed: " + err.message);
  }
  el("lastSync").textContent = "last sync " + new Date().toLocaleTimeString();
}

function setStatus(kind, text) {
  const light = el("statusLight");
  light.className = "status-light" + (kind !== "idle" ? " " + kind : "");
  el("statusText").textContent = text;
}

function restartPolling() {
  if (pollTimer) clearInterval(pollTimer);
  const secs = parseInt(el("intervalSelect").value, 10);
  localStorage.setItem(STORAGE_KEYS.interval, String(secs));
  if (secs > 0) {
    pollTimer = setInterval(pingEndpoint, secs * 1000);
  }
}

async function loadSampleData() {
  try {
    const res = await fetch("sample_data/sample_games.json", { cache: "no-store" });
    const arr = await res.json();
    const added = mergeGames(arr.map(normalizeGame));
    setStatus("ok", `loaded sample data — ${added} new game(s)`);
    render();
  } catch (err) {
    setStatus("error", "couldn't load sample data (are you opening this over file://? serve the folder instead, e.g. `python3 -m http.server`)");
  }
}

// ---- aggregation ----

function computeStats() {
  const total = games.length;
  const byWinner = { crewmates: 0, imposters: 0, timeout: 0, unknown: 0 };
  let totalKills = 0, totalEjections = 0, totalDuration = 0, durationCount = 0;

  const playerStats = new Map(); // name -> { games, wins, timesImposter, kills, color }

  for (const g of games) {
    const w = byWinner.hasOwnProperty(g.winner) ? g.winner : "unknown";
    byWinner[w]++;
    totalKills += g.kills || 0;
    totalEjections += g.ejections || 0;
    if (typeof g.duration_sec === "number") {
      totalDuration += g.duration_sec;
      durationCount++;
    }

    for (const p of g.players) {
      if (!playerStats.has(p.name)) {
        playerStats.set(p.name, { name: p.name, games: 0, wins: 0, timesImposter: 0, kills: 0, color: p.color });
      }
      const s = playerStats.get(p.name);
      s.games++;
      if (p.color && !s.color) s.color = p.color;
      if (p.imposter) s.timesImposter++;
      const won = (p.imposter && g.winner === "imposters") || (!p.imposter && g.winner === "crewmates");
      if (won) s.wins++;
    }
  }

  return {
    total,
    byWinner,
    totalKills,
    totalEjections,
    avgDuration: durationCount > 0 ? totalDuration / durationCount : null,
    players: [...playerStats.values()].sort((a, b) => (b.wins / b.games) - (a.wins / a.games) || b.games - a.games),
  };
}

// ---- rendering ----

function fmtDuration(sec) {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

function renderTiles(stats) {
  const crewmateWinRate = stats.total > 0 ? (stats.byWinner.crewmates / stats.total) * 100 : 0;
  const impostorWinRate = stats.total > 0 ? (stats.byWinner.imposters / stats.total) * 100 : 0;

  const tiles = [
    { label: "total games", value: stats.total, sub: "" },
    { label: "crewmate win rate", value: crewmateWinRate.toFixed(0) + "%", sub: `${stats.byWinner.crewmates} win(s)`, cls: "accent-crewmate" },
    { label: "imposter win rate", value: impostorWinRate.toFixed(0) + "%", sub: `${stats.byWinner.imposters} win(s)`, cls: "accent-impostor" },
    { label: "avg duration", value: fmtDuration(stats.avgDuration), sub: "" },
    { label: "total kills", value: stats.totalKills, sub: "" },
    { label: "total ejections", value: stats.totalEjections, sub: "" },
  ];

  el("tiles").innerHTML = tiles.map((t) => `
    <div class="tile ${t.cls || ""}">
      <div class="label">${t.label}</div>
      <div class="value">${t.value}</div>
      <div class="sub">${t.sub}</div>
    </div>
  `).join("");

  el("totalGamesLabel").textContent = `${stats.total} game${stats.total === 1 ? "" : "s"}`;
}

const WINNER_META = {
  crewmates: { label: "crewmates", color: "var(--crewmate)" },
  imposters: { label: "imposters", color: "var(--impostor)" },
  timeout: { label: "timeout", color: "var(--timeout)" },
  unknown: { label: "unknown", color: "var(--text-muted)" },
};

function renderChart(stats) {
  const max = Math.max(1, stats.total);
  const rows = Object.keys(WINNER_META)
    .filter((k) => stats.byWinner[k] > 0 || k !== "unknown")
    .map((key) => {
      const meta = WINNER_META[key];
      const count = stats.byWinner[key] || 0;
      const pct = (count / max) * 100;
      return `
        <div class="chart-row" data-tooltip="${meta.label}: ${count} game(s)">
          <span class="swatch" style="background:${meta.color}"></span>
          <span class="label">${meta.label}</span>
          <span class="track"><span class="fill" style="width:${pct}%; background:${meta.color}"></span></span>
          <span class="count">${count}</span>
        </div>
      `;
    });
  el("winChart").innerHTML = rows.join("");
  attachTooltips();
}

function renderPlayerTable(stats) {
  const body = el("playerTableBody");
  const empty = el("playerEmpty");
  if (stats.players.length === 0) {
    body.innerHTML = "";
    empty.classList.add("visible");
    return;
  }
  empty.classList.remove("visible");

  body.innerHTML = stats.players.map((p) => {
    const winRate = p.games > 0 ? (p.wins / p.games) * 100 : 0;
    const dotColor = p.color || "var(--text-muted)";
    return `
      <tr>
        <td><div class="player-name"><span class="player-dot" style="background:${dotColor}"></span>${p.name}</div></td>
        <td>${p.games}</td>
        <td>${p.wins}</td>
        <td>
          <div class="win-rate-cell">
            <span class="mini-track"><span class="mini-fill" style="width:${winRate}%"></span></span>
            <span>${winRate.toFixed(0)}%</span>
          </div>
        </td>
        <td>${p.timesImposter}</td>
        <td>${p.kills}</td>
      </tr>
    `;
  }).join("");
}

function renderFeed() {
  const feed = el("feed");
  const empty = el("feedEmpty");
  const recent = [...games].reverse().slice(0, 30);

  if (recent.length === 0) {
    feed.innerHTML = "";
    empty.classList.add("visible");
    return;
  }
  empty.classList.remove("visible");

  feed.innerHTML = recent.map((g) => {
    const ts = g.ended_at ? new Date(g.ended_at).toLocaleString() : "unknown time";
    const winnerClass = "winner-" + (WINNER_META[g.winner] ? g.winner : "unknown");
    return `
      <div class="feed-line">
        <span class="ts">${ts}</span>
        <span class="gid">${g.game_id || "GAME-???"}</span>
        winner: <span class="${winnerClass}">${g.winner}</span>
        <span class="meta">kills:${g.kills} ejections:${g.ejections} duration:${fmtDuration(g.duration_sec)}</span>
      </div>
    `;
  }).join("");
}

function render() {
  const stats = computeStats();
  renderTiles(stats);
  renderChart(stats);
  renderPlayerTable(stats);
  renderFeed();
}

// ---- tooltip (hover layer for the win-distribution bars) ----

function attachTooltips() {
  const tip = el("tooltip");
  document.querySelectorAll("[data-tooltip]").forEach((node) => {
    node.addEventListener("mousemove", (e) => {
      tip.textContent = node.getAttribute("data-tooltip");
      tip.style.left = e.clientX + "px";
      tip.style.top = e.clientY - 10 + "px";
      tip.classList.add("visible");
    });
    node.addEventListener("mouseleave", () => tip.classList.remove("visible"));
  });
}

// ---- theme toggle ----

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(STORAGE_KEYS.theme, theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(current === "dark" ? "light" : "dark");
}

// ---- init ----

function init() {
  loadGames();

  const savedTheme = localStorage.getItem(STORAGE_KEYS.theme) || "dark";
  applyTheme(savedTheme);

  const savedEndpoint = localStorage.getItem(STORAGE_KEYS.endpoint);
  if (savedEndpoint) el("endpointInput").value = savedEndpoint;

  const savedInterval = localStorage.getItem(STORAGE_KEYS.interval);
  if (savedInterval) el("intervalSelect").value = savedInterval;

  el("pingBtn").addEventListener("click", pingEndpoint);
  el("sampleBtn").addEventListener("click", loadSampleData);
  el("themeBtn").addEventListener("click", toggleTheme);
  el("clearBtn").addEventListener("click", () => {
    if (!confirm("Clear all locally stored match history?")) return;
    games = [];
    saveGames();
    render();
    setStatus("idle", "history cleared");
  });
  el("endpointInput").addEventListener("change", () => {
    localStorage.setItem(STORAGE_KEYS.endpoint, el("endpointInput").value.trim());
  });
  el("intervalSelect").addEventListener("change", restartPolling);

  render();
  restartPolling();
  if (el("endpointInput").value.trim()) {
    setStatus("idle", "ready — waiting for first ping");
  }
}

document.addEventListener("DOMContentLoaded", init);
