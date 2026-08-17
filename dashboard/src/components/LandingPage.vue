<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import AmongUsBean from "./landing/AmongUsBean.vue";
import StatTile from "./landing/StatTile.vue";
import PlayerCard from "./landing/PlayerCard.vue";

const { publicExperiments, loadPublicExperiments } = useFirestore();

const cycleIndex = ref(0);
let cycleTimer = null;
let refreshTimer = null;
let clockTimer = null;
const now = ref(new Date());

const current = computed(() => publicExperiments.value[cycleIndex.value] || null);

const players = computed(() => {
  const list = [...(current.value?.players || [])];
  return list.sort((a, b) => (b.wins || 0) - (a.wins || 0) || (b.games || 0) - (a.games || 0));
});

const mvp = computed(() => players.value[0]?.name || "—");

const totalGames = computed(() => current.value?.total_games || 0);
const byWinner = computed(() => current.value?.by_winner || {});
const crewWins = computed(() => byWinner.value.crewmates || 0);
const impWins = computed(() => byWinner.value.imposters || 0);
const crewPct = computed(() => (totalGames.value > 0 ? Math.round((crewWins.value / totalGames.value) * 100) : 0));
const impPct = computed(() => (totalGames.value > 0 ? Math.round((impWins.value / totalGames.value) * 100) : 0));

const recentGames = computed(() => {
  const g = current.value?.recent_games;
  const items = Array.isArray(g) ? g.slice(-8).reverse() : [];
  return items.concat(items); // duplicated so the marquee loops seamlessly
});

function fmtWinner(w) {
  if (w === "crewmates") return "[ CREW WIN ]";
  if (w === "imposters") return "[ IMPOSTER WIN ]";
  if (w === "timeout") return "[ TIMEOUT ]";
  return "[ " + (w || "?").toUpperCase() + " ]";
}
function winnerClass(w) {
  if (w === "crewmates") return "g";
  if (w === "imposters") return "r";
  return "a";
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

const clock = computed(() => now.value.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));

onMounted(async () => {
  document.title = "Among Us — Live Stats";
  await refresh();
  cycleTimer = setInterval(nextExperiment, 14000);
  refreshTimer = setInterval(refresh, 20000);
  clockTimer = setInterval(() => (now.value = new Date()), 1000);
});
onUnmounted(() => {
  clearInterval(cycleTimer);
  clearInterval(refreshTimer);
  clearInterval(clockTimer);
});
</script>

<template>
  <div class="tv-root">
    <div class="scanlines"></div>
    <div class="stars"></div>
    <div class="glow-blob a"></div>
    <div class="glow-blob b"></div>

    <div class="topbar">
      <span class="prompt">root@among-i<span class="dim">:~$</span> ./live_stats<span class="cursor">_</span></span>
      <div class="dots" v-if="publicExperiments.length > 1">
        <span
          v-for="(e, i) in publicExperiments"
          :key="e.studyId + e.id"
          class="dot"
          :class="{ active: i === cycleIndex }"
        ></span>
      </div>
      <span class="clock dim">{{ clock }}</span>
    </div>

    <!-- Empty state -->
    <div class="empty-state" v-if="!current">
      <AmongUsBean color="#4fe87c" size="9vw" />
      <div class="empty-title">[ waiting for the crew... ]</div>
      <div class="empty-sub">no games have finished yet — check back soon</div>
    </div>

    <template v-else>
      <section class="tiles-row">
        <StatTile icon="🎮" :value="totalGames" label="games played" accent="#7dd3fc" />
        <StatTile icon="🟢" :value="crewPct + '%'" label="crew win rate" accent="#4fe87c" />
        <StatTile icon="🔴" :value="impPct + '%'" label="imposter win rate" accent="#ff5c5c" />
        <StatTile icon="🔪" :value="current.total_kills || 0" label="total kills" accent="#ffb454" />
        <StatTile icon="🚪" :value="current.total_ejections || 0" label="ejections" accent="#c084fc" />
        <StatTile icon="👑" :value="mvp" label="top player" accent="#ffd85e" />
      </section>

      <section class="players-wrap">
        <div class="section-label">[ players ]</div>
        <div class="players-grid">
          <PlayerCard
            v-for="(p, i) in players"
            :key="p.name + i"
            :player="p"
            :rank="i + 1"
          />
          <div class="no-players dim" v-if="!players.length">no players recorded yet</div>
        </div>
      </section>

      <footer class="ticker-wrap" v-if="recentGames.length">
        <div class="ticker-label">recent</div>
        <div class="ticker-viewport">
          <div class="ticker-track">
            <span class="ticker-item" :class="winnerClass(g.winner)" v-for="(g, i) in recentGames" :key="i">
              {{ fmtWinner(g.winner) }}&nbsp;&nbsp;🔪&nbsp;{{ g.kills || 0 }} kills&nbsp;&nbsp;🚪&nbsp;{{ g.ejections || 0 }} ejections
            </span>
          </div>
        </div>
      </footer>
    </template>

    <a class="dev-bar" href="/dashboard">
      <span class="dev-bar-icon">🛠️</span>
      <span class="dev-bar-text">developer dashboard — configs, jobs &amp; server admin</span>
      <span class="dev-bar-arrow">→</span>
    </a>
  </div>
</template>

<style scoped>
.tv-root {
  --font-mono: "SF Mono", "JetBrains Mono", "Fira Code", ui-monospace, Menlo, Consolas, monospace;
  position: fixed; inset: 0; overflow: hidden;
  background: radial-gradient(ellipse at 50% -10%, #101c30 0%, #0a1020 55%, #05070d 100%);
  color: #dce6f5;
  font-family: var(--font-mono);
  display: flex; flex-direction: column;
  padding: 1.8vh 2.4vw 1.4vh;
  gap: 1.6vh;
}

.scanlines {
  position: absolute; inset: 0; pointer-events: none; z-index: 2;
  background: repeating-linear-gradient(
    to bottom, rgba(255,255,255,0.025) 0px, rgba(255,255,255,0.025) 1px,
    transparent 1px, transparent 3px
  );
  mix-blend-mode: overlay;
}

.stars {
  position: absolute; inset: -20%;
  background-image:
    radial-gradient(1.6px 1.6px at 40px 60px, #fff, transparent),
    radial-gradient(1.2px 1.2px at 160px 120px, #fff, transparent),
    radial-gradient(1.8px 1.8px at 260px 40px, #fff, transparent),
    radial-gradient(1.2px 1.2px at 320px 200px, #fff, transparent),
    radial-gradient(1.4px 1.4px at 90px 240px, #fff, transparent);
  background-repeat: repeat; background-size: 340px 300px;
  opacity: 0.5; animation: drift 140s linear infinite; pointer-events: none;
}
@keyframes drift { from { transform: translate(0, 0); } to { transform: translate(-340px, -300px); } }

.glow-blob {
  position: absolute; border-radius: 50%; filter: blur(70px); opacity: 0.22; pointer-events: none;
}
.glow-blob.a { width: 32vw; height: 32vw; background: #4fe87c; top: -10vw; left: -6vw; }
.glow-blob.b { width: 28vw; height: 28vw; background: #ff5c5c; bottom: -10vw; right: -4vw; }

/* ── Top bar ─────────────────────────────────────────────── */
.topbar {
  display: flex; align-items: center; justify-content: space-between; z-index: 1;
  font-size: 1.1vw; color: #4fe87c; text-shadow: 0 0 10px rgba(79,232,124,0.5);
  letter-spacing: 0.02em; flex-shrink: 0;
}
.prompt .dim { color: #6b7590; text-shadow: none; }
.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
.clock { font-size: 1vw; text-shadow: none; flex-shrink: 0; }
.topbar .dots { position: static; transform: none; }

/* ── Empty state ─────────────────────────────────────────── */
.empty-state {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1.2vh; z-index: 1;
}
.empty-title { font-size: 2.2vw; font-weight: 700; color: #4fe87c; text-shadow: 0 0 12px rgba(79,232,124,0.5); }
.empty-sub { font-size: 1.1vw; color: #a8b3c7; }

/* ── Tiles ───────────────────────────────────────────────── */
.tiles-row { display: flex; gap: 1.3vw; justify-content: center; flex-wrap: wrap; z-index: 1; flex-shrink: 0; }

/* ── Players ─────────────────────────────────────────────── */
.players-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; z-index: 1; }
.section-label {
  font-size: 1.1vw; letter-spacing: 0.08em; color: #4fe87c; text-shadow: 0 0 8px rgba(79,232,124,0.4);
  margin-bottom: 1vh; flex-shrink: 0;
}
.players-grid {
  flex: 1; min-height: 0; overflow-y: auto;
  display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 260px));
  gap: 3vh 1.6vw; align-content: center; justify-content: center;
}
.players-grid::-webkit-scrollbar { width: 4px; }
.players-grid::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }
.no-players { grid-column: 1 / -1; text-align: center; padding: 2vh; font-size: 1.1vw; }
.dim { color: #a8b3c7; }

/* ── Ticker ──────────────────────────────────────────────── */
.ticker-wrap {
  display: flex; align-items: center; z-index: 1; flex-shrink: 0;
  border-top: 1px solid rgba(79,232,124,0.2); padding-top: 1vh;
  gap: 1vw;
}
.ticker-label {
  flex-shrink: 0; font-size: 0.9vw; text-transform: uppercase; letter-spacing: 0.12em;
  color: #4fe87c; border: 1px solid rgba(79,232,124,0.35); padding: 0.4vh 0.9vw; border-radius: 4px;
}
.ticker-viewport { flex: 1; min-width: 0; overflow: hidden; }
.ticker-track {
  display: flex; white-space: nowrap; animation: scroll-left 26s linear infinite;
  font-size: 1vw; width: max-content;
}
.ticker-item { padding: 0 1.6vw; border-right: 1px solid rgba(255,255,255,0.12); }
.ticker-item.g { color: #6dffb0; }
.ticker-item.r { color: #ff8f8f; }
.ticker-item.a { color: #ffd85e; }
@keyframes scroll-left { from { transform: translateX(0); } to { transform: translateX(-50%); } }

/* ── Dots ────────────────────────────────────────────────── */
.dots { display: flex; gap: 0.5vw; z-index: 1; }
.dot { width: 0.5vw; height: 0.5vw; border-radius: 50%; background: rgba(255,255,255,0.25); }
.dot.active { background: #4fe87c; box-shadow: 0 0 8px rgba(79,232,124,0.7); }

/* ── Dev bar ─────────────────────────────────────────────── */
.dev-bar {
  flex-shrink: 0; z-index: 1;
  display: flex; align-items: center; justify-content: center; gap: 0.7vw;
  padding: 1vh 1vw; margin-top: -0.4vh;
  border: 1px solid rgba(79, 232, 124, 0.35);
  border-radius: 8px;
  background: rgba(79, 232, 124, 0.06);
  color: #cfe9d8;
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 1vw;
  letter-spacing: 0.02em;
  transition: all 0.15s ease;
}
.dev-bar:hover {
  background: rgba(79, 232, 124, 0.14);
  border-color: rgba(79, 232, 124, 0.7);
  box-shadow: 0 0 16px rgba(79, 232, 124, 0.3);
}
.dev-bar-icon { font-size: 1.1vw; }
.dev-bar-text { color: #eef2ff; }
.dev-bar-arrow { color: #4fe87c; font-weight: 700; transition: transform 0.15s ease; }
.dev-bar:hover .dev-bar-arrow { transform: translateX(4px); }
</style>
