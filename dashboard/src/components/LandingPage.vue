<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import { winningGroups, groupWins, sortedPlayers, paletteCls, fmtWinner } from "../composables/experimentStats.js";
import TerminalCard from "./TerminalCard.vue";
import AmongUsBean from "./landing/AmongUsBean.vue";
import StatTile from "./landing/StatTile.vue";
import PlayerCard from "./landing/PlayerCard.vue";

const { publicExperiments, loadPublicExperiments, servers, startServerWatch, stopServerWatch } = useFirestore();

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
    <div class="about-wrap">
      <TerminalCard title="about" :min-width="80" :collapsible="false">
        <div class="about dim">
          among-i is a multi-agent LLM simulation: agents with distinct personalities
          play among us-style rounds — every move, chat, kill, and vote is decided by a
          language model. this page shows live stats from finished experiments.
        </div>
      </TerminalCard>
    </div>

    <!-- Empty state -->
    <TerminalCard v-if="!current" title="live stats" :min-width="60" :collapsible="false">
      <div class="empty-state">
        <AmongUsBean color="#4fe87c" size="150px" />
        <div class="empty-title g">[ waiting for the crew... ]</div>
        <div class="dim">no games have finished yet — check back soon</div>
      </div>
    </TerminalCard>

    <template v-else>
      <section class="tiles-row">
        <StatTile icon="🎮" :value="totalGames" label="games played" accent="var(--blue)" />
        <StatTile
          v-for="g in groupStats"
          :key="g.key"
          :icon="g.cls === 'r' ? '🔴' : g.cls === 'g' ? '🟢' : '🏳️'"
          :value="g.pct + '%'"
          :label="g.label + ' win rate'"
          :accent="accentFor(g.cls)"
        />
        <StatTile icon="🔪" :value="current.total_kills || 0" label="total kills" accent="var(--amber)" />
        <StatTile icon="🚪" :value="current.total_ejections || 0" label="ejections" accent="var(--purple)" />
        <StatTile icon="👑" :value="mvp" label="top player" accent="var(--yellow, var(--amber))" />
      </section>

      <TerminalCard title="servers" :min-width="80" :collapsible="false">
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

      <div class="players-outer">
        <TerminalCard
          :title="'players · ' + (current.studyName || current.studyId) + '/' + current.id"
          :min-width="80"
          :collapsible="false"
        >
          <div class="players-grid">
            <PlayerCard
              v-for="(p, i) in players"
              :key="p.name + i"
              :player="p"
              :rank="i + 1"
            />
            <div class="no-players dim" v-if="!players.length">no players recorded yet</div>
          </div>
        </TerminalCard>
      </div>

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
    </template>
  </div>
</template>

<style scoped>
.landing {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column; gap: var(--sp-md);
  font-family: var(--font-mono);
}

/* ── About ───────────────────────────────────────────────── */
.about-wrap { display: flex; justify-content: center; }
.about {
  font-size: var(--fs-base); line-height: var(--lh-loose);
  white-space: normal; word-break: normal;
}

/* The box-expand clip-path animation can stall mid-frame on this busy
   page and leave cards visibly sliced — render landing cards instantly. */
.landing :deep(.card-box) { animation: none; }

/* ── Empty state ─────────────────────────────────────────── */
.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--sp-sm); padding: var(--sp-md) 0;
}
.empty-title { font-size: var(--fs-md); font-weight: 700; }

/* ── Tiles ───────────────────────────────────────────────── */
.tiles-row {
  display: flex; gap: var(--sp-sm); justify-content: center; flex-wrap: wrap;
  flex-shrink: 0;
}

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

/* ── Players ─────────────────────────────────────────────── */
.players-outer { flex: 1; min-height: 0; overflow-y: auto; display: flex; }
.players-outer > * { flex: 1; }
.players-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 280px));
  gap: var(--sp-sm); justify-content: center;
}
.no-players { grid-column: 1 / -1; text-align: center; padding: var(--sp-md); }

/* ── Ticker — pinned to the bottom ───────────────────────── */
.ticker-wrap {
  display: flex; align-items: center; flex-shrink: 0; margin-top: auto;
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
</style>
