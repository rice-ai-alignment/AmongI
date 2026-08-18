<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import { winningGroups, groupWins, sortedPlayers, paletteCls, fmtWinner } from "../composables/experimentStats.js";
import TerminalCard from "./TerminalCard.vue";
import AmongUsBean from "./landing/AmongUsBean.vue";
import StatTile from "./landing/StatTile.vue";
import PlayerCard from "./landing/PlayerCard.vue";

const { publicExperiments, publicLoading, loadPublicExperiments, servers, startServerWatch, stopServerWatch } = useFirestore();

const cycleIndex = ref(0);
let cycleTimer = null;
let refreshTimer = null;
let serverTick = null;
const nowTick = ref(Date.now());

const current = computed(() => publicExperiments.value[cycleIndex.value] || null);

// ── Server states ─────────────────────────────────────────────
const SERVER_STYLES = {
  online:  { color: "#4fe87c", label: "online" },
  busy:    { color: "#ffb454", label: "busy" },
  offline: { color: "#5a5a5a", label: "offline" },
};

function serverState(s) {
  if (!s.last_seen) return "offline";
  const interval = (s.heartbeat_interval_sec || 30) * 1000;
  const last = s.last_seen.toDate ? s.last_seen.toDate().getTime() : Date.parse(s.last_seen);
  if (isNaN(last)) return "offline";
  if (nowTick.value - last > interval * 2 + 15000) return "offline";
  return s.status === "busy" ? "busy" : "online";
}

const serverChips = computed(() =>
  [...servers.value]
    .sort((a, b) => (a.id || "").localeCompare(b.id || ""))
    .map((s) => {
      const state = serverState(s);
      return { id: s.id, state, ...SERVER_STYLES[state], jobs: s.jobs_completed || 0 };
    })
);

// Winning groups come from the experiment config, not hardcoded names
const groups = computed(() => winningGroups(current.value?.config));
const groupStats = computed(() => groupWins(current.value, groups.value));

const players = computed(() => sortedPlayers(current.value));
const mvp = computed(() => players.value[0]?.name || "—");
const totalGames = computed(() => current.value?.total_games || 0);
const playersTitle = computed(() =>
  current.value
    ? "players · " + (current.value.studyName || current.value.studyId) + "/" + current.value.id
    : "players · (loading)"
);

const recentGames = computed(() => {
  const g = current.value?.recent_games;
  const items = Array.isArray(g) ? g.slice(-8).reverse() : [];
  return items.concat(items); // duplicated so the marquee loops seamlessly
});

function accentFor(cls) {
  if (cls === "r") return "var(--red)";
  if (cls === "g") return "var(--green)";
  return "var(--amber)";
}

function nextExperiment() {
  if (publicExperiments.value.length < 2) return;
  cycleIndex.value = (cycleIndex.value + 1) % publicExperiments.value.length;
}

async function refresh() {
  const before = current.value?.id;
  await loadPublicExperiments();
  if (cycleIndex.value >= publicExperiments.value.length) cycleIndex.value = 0;
  if (before) {
    const idx = publicExperiments.value.findIndex((e) => e.id === before && e.studyId === current.value?.studyId);
    if (idx >= 0) cycleIndex.value = idx;
  }
}

onMounted(async () => {
  await refresh();
  startServerWatch();
  cycleTimer = setInterval(nextExperiment, 14000);
  refreshTimer = setInterval(refresh, 20000);
  serverTick = setInterval(() => (nowTick.value = Date.now()), 1000);
});
onUnmounted(() => {
  clearInterval(cycleTimer);
  clearInterval(refreshTimer);
  clearInterval(serverTick);
  stopServerWatch();
});
</script>

<template>
  <div class="landing">
    <!-- The full layout renders immediately (before experiments load);
         values fill in as the data arrives. -->
    <!-- Left side column: about, lab cards, stat tiles, servers -->
    <aside class="side-col">
      <TerminalCard title="about" :min-width="40" :collapsible="false">
        <div class="about dim">
          raia labs is the experimental division of <b>rice ai alignment</b> — a student
          club at rice university. our members create, deploy, and analyze agentic
          experiments: llm-driven agents with their own personas act in simulated
          worlds, and every decision, conversation, and outcome is recorded.
        </div>
      </TerminalCard>

      <TerminalCard title="[01] create" :min-width="40" :collapsible="false">
        <div class="about dim">
          design experiments with a modular config system — agent personas, maps,
          actions, phases, and win conditions — validated by a shared schema compiler.
        </div>
      </TerminalCard>

      <TerminalCard title="[02] deploy" :min-width="40" :collapsible="false">
        <div class="about dim">
          queue jobs to the lab server fleet: workers claim trials, run games against
          live llms, and stream a godot render view of the action.
        </div>
      </TerminalCard>

      <TerminalCard title="[03] analyze" :min-width="40" :collapsible="false">
        <div class="about dim">
          every trial is logged — per-game stats, full context and decision traces,
          and win rates per group — inspectable right here in the dashboard.
        </div>
      </TerminalCard>

      <TerminalCard title="live stats" :min-width="40" :collapsible="false">
        <div class="tiles-grid">
          <StatTile icon="🎮" :value="totalGames" label="games played" accent="var(--blue)" />
          <StatTile
            v-for="g in groupStats"
            :key="g.key"
            :icon="g.cls === 'r' ? '🔴' : g.cls === 'g' ? '🟢' : '🏳️'"
            :value="g.pct + '%'"
            :label="g.label + ' win rate'"
            :accent="accentFor(g.cls)"
          />
          <StatTile icon="🔪" :value="current?.total_kills || 0" label="total kills" accent="var(--amber)" />
          <StatTile icon="🚪" :value="current?.total_ejections || 0" label="ejections" accent="var(--purple)" />
          <StatTile icon="👑" :value="mvp" label="top player" accent="var(--yellow, var(--amber))" />
        </div>
      </TerminalCard>

      <TerminalCard title="servers" :min-width="40" :collapsible="false">
        <div class="server-row">
          <div v-for="s in serverChips" :key="s.id" class="server-chip">
            <AmongUsBean :color="s.color" size="34px" />
            <div class="server-info">
              <span class="server-name">{{ s.id }}</span>
              <span class="dim server-state" :style="{ color: s.state === 'offline' ? 'var(--text-dim)' : s.color }">
                {{ s.label }} · {{ s.jobs }} jobs
              </span>
            </div>
          </div>
          <div v-if="!serverChips.length" class="dim no-servers">(no servers connected)</div>
        </div>
      </TerminalCard>
    </aside>

    <!-- Main column: players fill the remaining space -->
    <section class="main-col">
      <TerminalCard
        :title="playersTitle"
        :min-width="60"
        :collapsible="false"
        class="players-card"
      >
        <div class="players-grid">
          <PlayerCard
            v-for="(p, i) in players"
            :key="p.name + i"
            :player="p"
            :rank="i + 1"
          />
          <div class="no-players" v-if="!players.length">
            <AmongUsBean color="#4fe87c" size="80px" />
            <div class="empty-title g">{{ publicLoading ? "[ loading... ]" : "[ waiting for the crew... ]" }}</div>
            <div class="dim">{{ publicLoading ? "fetching experiment stats" : "no games have finished yet — check back soon" }}</div>
          </div>
        </div>
      </TerminalCard>
    </section>

    <footer class="ticker-wrap" v-if="recentGames.length">
      <div class="ticker-label">recent</div>
      <div class="ticker-viewport">
        <div class="ticker-track">
          <span class="ticker-item" :class="paletteCls(g.winner)" v-for="(g, i) in recentGames" :key="i">
            {{ fmtWinner(g.winner, groups) }}&nbsp;&nbsp;🔪&nbsp;{{ g.kills || 0 }} kills&nbsp;&nbsp;🚪&nbsp;{{ g.ejections || 0 }} ejections
          </span>
        </div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.landing {
  flex: 1; min-height: 0;
  display: grid;
  grid-template-columns: minmax(300px, 5fr) minmax(0, 7fr);
  grid-template-rows: 1fr auto;
  gap: var(--sp-md);
  font-family: var(--font-mono);
}

/* The box-expand clip-path animation can stall mid-frame on this busy
   page and leave cards visibly sliced — render landing cards instantly. */
.landing :deep(.card-box) { animation: none; margin-bottom: 0; }

/* Cards size themselves with an inline ch-width; make them fill their
   grid cell instead so the two columns span the whole screen. */
.side-col :deep(.card-box),
.main-col :deep(.card-box) { width: 100% !important; }

/* ── Loading / empty state (inside the players card) ─────── */
.no-players {
  grid-column: 1 / -1;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--sp-sm); padding: var(--sp-lg) var(--sp-md);
}
.empty-title { font-size: var(--fs-md); font-weight: 700; }

/* ── Left side column ────────────────────────────────────── */
.side-col {
  min-height: 0; overflow-y: auto;
  display: flex; flex-direction: column; gap: var(--sp-md);
  padding-right: 2px;
}
.side-col::-webkit-scrollbar { width: var(--scrollbar-w, 3px); }
.side-col::-webkit-scrollbar-thumb { background: var(--border); border-radius: var(--radius-sm); }
.side-col::-webkit-scrollbar-track { background: transparent; }

.about {
  font-size: var(--fs-base); line-height: var(--lh-loose);
  white-space: normal; word-break: normal;
}

/* ── Tiles (grid inside the side column) ─────────────────── */
.tiles-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--sp-xs);
}
.tiles-grid > * { min-width: 0; }

/* ── Servers ─────────────────────────────────────────────── */
.server-row {
  display: flex; flex-wrap: wrap; gap: var(--sp-sm); align-items: center;
}
.server-chip {
  display: flex; align-items: center; gap: var(--sp-xxs);
  padding: var(--sp-xxs) var(--sp-sm);
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
}
.server-info { display: flex; flex-direction: column; }
.server-name { font-size: var(--fs-base); }
.server-state { font-size: var(--fs-sm); }
.no-servers { padding: var(--sp-xxs) var(--sp-sm); }

/* ── Main column: players fill the remaining space ───────── */
.main-col { min-height: 0; display: flex; }
.main-col > * { flex: 1; min-width: 0; }
.main-col :deep(.card-box) {
  height: 100%; display: flex; flex-direction: column;
  overflow-y: hidden;
}
.main-col :deep(.box-body) {
  flex: 1; min-height: 0; overflow-y: auto; display: flex;
}
.main-col :deep(.box-body)::-webkit-scrollbar { width: var(--scrollbar-w, 3px); }
.main-col :deep(.box-body)::-webkit-scrollbar-thumb { background: var(--border); border-radius: var(--radius-sm); }
.main-col :deep(.box-body)::-webkit-scrollbar-track { background: transparent; }

.players-grid {
  flex: 1; min-height: 0; align-content: start;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: var(--sp-sm);
}

/* ── Ticker — pinned to the bottom, spans both columns ───── */
.ticker-wrap {
  grid-column: 1 / -1;
  display: flex; align-items: center; flex-shrink: 0;
  border-top: var(--border-hair); padding-top: var(--sp-xs); gap: var(--sp-sm);
}
.ticker-label {
  flex-shrink: 0; font-size: var(--fs-sm); text-transform: uppercase;
  letter-spacing: 0.12em; color: var(--green);
  border: var(--border-subtle); padding: 2px var(--sp-sm); border-radius: var(--radius-sm);
}
.ticker-viewport { flex: 1; min-width: 0; overflow: hidden; }
.ticker-track {
  display: flex; white-space: nowrap; animation: scroll-left 26s linear infinite;
  font-size: var(--fs-base); width: max-content;
}
.ticker-item { padding: 0 var(--sp-lg); border-right: var(--border-hair); }
@keyframes scroll-left { from { transform: translateX(0); } to { transform: translateX(-50%); } }

/* ── Narrow windows: single column stack ─────────────────── */
@media (max-width: 900px) {
  .landing { grid-template-columns: 1fr; }
  .ticker-wrap { grid-column: 1; }
  .side-col { overflow-y: visible; }
  .main-col { min-height: 45vh; }
}
</style>
