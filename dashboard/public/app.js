// among-i match stats dashboard
// Reads pre-computed stats directly from Firestore — no local storage needed.
//
// For local dev, copy firebase-config.example.js to firebase-config.js (gitignored)
// with:  const FIREBASE_CONFIG = { apiKey: "...", projectId: "..." };

const FIRESTORE_COLLECTION = "experiments";
let _experimentId = null;
let _stats = null;
let _games = [];
let pollTimer = null;

const el = (id) => document.getElementById(id);

// ---- Firestore ----

let _firestore = null;
let _firebaseDisabled = false;

function getFirestore() {
  if (_firestore) return _firestore;
  if (_firebaseDisabled) return null;
  try {
    if (typeof firebase === "undefined" || !firebase.apps || !firebase.firestore) {
      console.log("[dashboard] Firebase SDK not loaded — running offline");
      _firebaseDisabled = true;
      return null;
    }
    if (!firebase.apps.length) {
      if (typeof FIREBASE_CONFIG !== "undefined") {
        firebase.initializeApp(FIREBASE_CONFIG);
      } else {
        console.log("[dashboard] No firebase-config.js found — running offline");
        _firebaseDisabled = true;
        return null;
      }
    }
    _firestore = firebase.firestore();
  } catch (e) {
    console.log("[dashboard] Firestore unavailable — running offline");
    _firebaseDisabled = true;
    return null;
  }
  return _firestore;
}

async function discoverExperiment() {
  const db = getFirestore();
  if (!db) return false;
  try {
    const snaps = await db.collection(FIRESTORE_COLLECTION)
      .orderBy("updated_at", "desc").limit(1).get();
    if (snaps.empty) return false;
    _experimentId = snaps.docs[0].id;
    console.log("[dashboard] Latest experiment:", _experimentId);
    return true;
  } catch (e) {
    console.warn("[dashboard] Experiment discovery failed:", e.message);
    return false;
  }
}

async function fetchFromFirestore() {
  const db = getFirestore();
  if (!db || !_experimentId) return false;
  try {
    // Fetch pre-computed stats document
    const statsSnap = await db.collection(FIRESTORE_COLLECTION).doc(_experimentId).get();
    if (statsSnap.exists) {
      _stats = statsSnap.data();
    }

    // Fetch games for the feed
    const gamesSnap = await db.collection(FIRESTORE_COLLECTION)
      .doc(_experimentId).collection("games").orderBy("ended_at").get();
    _games = [];
    gamesSnap.forEach(doc => _games.push(doc.data()));

    setStatus("ok", `${_stats?.total_games || 0} games · ${_experimentId}`);
    el("lastSync").textContent = "last sync " + new Date().toLocaleTimeString();
    render();
    return true;
  } catch (e) {
    setStatus("error", "Firestore read failed: " + e.message);
    return false;
  }
}

// ---- polling ----

function restartPolling() {
  if (pollTimer) clearInterval(pollTimer);
  const secs = parseInt(el("intervalSelect").value, 10);
  localStorage.setItem(STORAGE_KEYS.interval, String(secs));
  if (secs > 0) {
    pollTimer = setInterval(fetchFromFirestore, secs * 1000);
  }
}

function setStatus(kind, text) {
  const light = el("statusLight");
  light.className = "status-light" + (kind !== "idle" ? " " + kind : "");
  el("statusText").textContent = text;
}

// ---- rendering ----

function fmtDuration(sec) {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

function renderTiles() {
  const s = _stats || {};
  const total = s.total_games || 0;
  const byWinner = s.by_winner || {};
  const crewWins = byWinner.crewmates || 0;
  const impWins = byWinner.imposters || 0;
  const crewRate = total > 0 ? (crewWins / total) * 100 : 0;
  const impRate = total > 0 ? (impWins / total) * 100 : 0;

  const tiles = [
    { label: "total games", value: total, sub: "" },
    { label: "crewmate win rate", value: crewRate.toFixed(0) + "%", sub: `${crewWins} win(s)`, cls: "accent-crewmate" },
    { label: "imposter win rate", value: impRate.toFixed(0) + "%", sub: `${impWins} win(s)`, cls: "accent-impostor" },
    { label: "avg duration", value: "—", sub: "" },
    { label: "total kills", value: s.total_kills || 0, sub: "" },
    { label: "total ejections", value: s.total_ejections || 0, sub: "" },
  ];

  el("tiles").innerHTML = tiles.map((t) => `
    <div class="tile ${t.cls || ""}">
      <div class="label">${t.label}</div>
      <div class="value">${t.value}</div>
      <div class="sub">${t.sub}</div>
    </div>
  `).join("");

  el("totalGamesLabel").textContent = `${total} game${total === 1 ? "" : "s"}`;
}

const WINNER_META = {
  crewmates: { label: "crewmates", color: "var(--crewmate)" },
  imposters: { label: "imposters", color: "var(--impostor)" },
  timeout: { label: "timeout", color: "var(--timeout)" },
  token_limit: { label: "token limit", color: "var(--token-limit)" },
  unknown: { label: "unknown", color: "var(--text-muted)" },
};

function renderChart() {
  const byWinner = (_stats && _stats.by_winner) || {};
  const total = _stats?.total_games || 0;
  const max = Math.max(1, total);
  const rows = Object.keys(WINNER_META)
    .filter((k) => byWinner[k] > 0 || k !== "unknown")
    .map((key) => {
      const meta = WINNER_META[key];
      const count = byWinner[key] || 0;
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

function renderPlayerTable() {
  const players = (_stats && _stats.players) || [];
  const body = el("playerTableBody");
  const empty = el("playerEmpty");
  if (players.length === 0) {
    body.innerHTML = "";
    empty.classList.add("visible");
    return;
  }
  empty.classList.remove("visible");

  body.innerHTML = players.map((p) => {
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
        <td>${p.times_imposter}</td>
        <td>${p.kills}</td>
      </tr>
    `;
  }).join("");
}

function renderFeed() {
  const feed = el("feed");
  const empty = el("feedEmpty");
  const recent = [..._games].reverse().slice(0, 30);

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
  renderTiles();
  renderChart();
  renderPlayerTable();
  renderFeed();
}

// ---- tooltip ----

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

// ---- theme ----

const STORAGE_KEYS = {
  interval: "amongi_dashboard_interval",
  theme: "amongi_dashboard_theme",
};

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(STORAGE_KEYS.theme, theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(current === "dark" ? "light" : "dark");
}

// ---- sample data (offline testing) ----

async function loadSampleData() {
  try {
    const res = await fetch("sample_data/sample_games.json", { cache: "no-store" });
    const arr = await res.json();
    // Fake stats for sample mode
    const byWinner = { crewmates: 0, imposters: 0, timeout: 0, token_limit: 0 };
    const players = {};
    for (const g of arr) {
      const w = g.winner || "unknown";
      if (byWinner.hasOwnProperty(w)) byWinner[w]++;
      for (const p of (g.players || [])) {
        const name = p.name || "?";
        if (!players[name]) players[name] = { name, games: 0, wins: 0, times_imposter: 0, kills: 0, color: p.color };
        players[name].games++;
        if (p.imposter) players[name].times_imposter++;
        players[name].kills += p.kills || 0;
        if ((p.imposter && w === "imposters") || (!p.imposter && w === "crewmates")) players[name].wins++;
      }
    }
    _stats = {
      total_games: arr.length,
      total_kills: arr.reduce((s, g) => s + (g.kills || 0), 0),
      total_ejections: arr.reduce((s, g) => s + (g.ejections || 0), 0),
      by_winner: byWinner,
      players: Object.values(players).sort((a, b) => (b.wins / b.games) - (a.wins / a.games) || b.games - a.games),
    };
    _games = arr;
    setStatus("ok", `loaded sample data — ${arr.length} game(s)`);
    render();
  } catch (err) {
    setStatus("error", "couldn't load sample data");
  }
}

// ---- init ----

async function init() {
  const savedTheme = localStorage.getItem(STORAGE_KEYS.theme) || "dark";
  applyTheme(savedTheme);

  const savedInterval = localStorage.getItem(STORAGE_KEYS.interval);
  if (savedInterval) el("intervalSelect").value = savedInterval;

  el("sampleBtn").addEventListener("click", loadSampleData);
  el("themeBtn").addEventListener("click", toggleTheme);
  el("clearBtn").addEventListener("click", () => {
    setStatus("idle", "all data lives in Firestore — nothing to clear locally");
  });
  el("intervalSelect").addEventListener("change", restartPolling);

  const found = await discoverExperiment();
  if (found) {
    setStatus("ok", `connected · ${_experimentId}`);
    await fetchFromFirestore();
  } else {
    setStatus("idle", "no experiment found — waiting for data");
  }

  render();
  restartPolling();
}

document.addEventListener("DOMContentLoaded", init);
