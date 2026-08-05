<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { useFirestore } from "./composables/useFirestore.js";
import TypedSpan from "./components/TypedSpan.vue";
import { TYPE } from "./composables/typeSettings.js";
import StudyBrowser from "./components/StudyBrowser.vue";
import TilesSection from "./components/TilesSection.vue";
import WinChart from "./components/WinChart.vue";
import PlayerTable from "./components/PlayerTable.vue";
import MatchFeed from "./components/MatchFeed.vue";

const {
  user, authReady, initAuth, signIn, signOut,
  studies, activeStudyId, loadStudies, studyExperiments, loadAllExperiments,
  experiments, activeExperimentId, loadExperiments,
  stats, games, statusKind, statusText, lastSync, fetchData,
} = useFirestore();

const browsing = ref(true);
const interval = ref(10);
let pollTimer = null;

// Shared box width — components register their max line length here
// Resolve display names from IDs for the titlebar path
const studyName = computed(() => studies.value.find(s => s.id === activeStudyId.value)?.name || activeStudyId.value);
const expName = computed(() => experiments.value.find(e => e.id === activeExperimentId.value)?.name || activeExperimentId.value);

// Titlebar path
const pathText = computed(() => {
  let p = "~/studies";
  if (activeStudyId.value) p += "/" + studyName.value;
  if (activeExperimentId.value) p += "/" + expName.value;
  return p;
});

function restartPolling() {
  if (pollTimer) clearInterval(pollTimer);
  if (interval.value > 0 && activeExperimentId.value) {
    pollTimer = setInterval(fetchData, interval.value * 1000);
  }
}
// Sync URL path with current navigation state
function syncURL() {
  let path = "/studies";
  if (activeStudyId.value) {
    path += "/" + (studyName.value || activeStudyId.value);
    if (activeExperimentId.value) {
      path += "/" + (expName.value || activeExperimentId.value);
    }
  }
  window.history.replaceState({}, "", path);
}

watch(activeExperimentId, async (id) => {
  if (id) {
    // Clear old data immediately so stale stats don't flash
    stats.value = null;
    games.value = [];
    await loadExperiments();
    await fetchData();
    restartPolling();
    syncURL();
  }
});
watch(activeStudyId, async (id) => {
  if (id) {
    await loadExperiments();
    await loadAllExperiments();
    syncURL();
  } else {
    syncURL();
  }
});

onMounted(async () => {
  initAuth();
  await loadStudies();
  await loadAllExperiments();
  restartPolling();

  // Restore navigation state from URL
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (parts[0] === "studies" && parts[1]) {
    const s = studies.value.find(s => s.id === parts[1] || s.name === parts[1]);
    if (s) {
      activeStudyId.value = s.id;
      await loadExperiments();
      if (parts[2]) {
        const e = experiments.value.find(e => e.id === parts[2] || e.name === parts[2]);
        if (e) {
          activeExperimentId.value = e.id;
          browsing.value = false;
          await fetchData();
        }
      }
    }
  }
  syncURL();
});
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer); });
</script>

<template>
  <!-- Terminal window -->
  <div class="terminal">
    <!-- Title bar -->
    <div class="term-titlebar">
      <span class="tb-title">
        RAIA LABS
        <span class="tb-path"><TypedSpan :text="pathText" :speed="TYPE.normal" :key="pathText" /></span>
      </span>
      <span class="tb-actions">
        <template v-if="user">
          <span class="tb-user">{{ user.displayName }}</span>
          <button class="tb-btn" @click="signOut">logout</button>
        </template>
        <button v-else class="tb-btn" @click="signIn" :disabled="!authReady">login</button>
      </span>
    </div>

    <!-- Terminal body -->
    <div class="term-body">
      <!-- Status line -->
      <div class="term-status">
        <span class="status-light" :class="statusKind !== 'idle' ? statusKind : ''"></span>
        <span>{{ statusText }}</span>
        <span class="dim"> · {{ lastSync }}</span>
        <span class="spacer"></span>
        <span class="dim">poll:</span>
        <select v-model.number="interval" @change="restartPolling" class="term-select">
          <option :value="5">5s</option>
          <option :value="10">10s</option>
          <option :value="30">30s</option>
          <option :value="60">60s</option>
          <option :value="0">off</option>
        </select>
      </div>

      <div class="term-content">
        <StudyBrowser @browsing="browsing = $event" />
        <Transition name="fade">
          <div v-if="!browsing && activeExperimentId" :key="activeExperimentId" class="main-content type-block">
            <TilesSection :stats="stats" />
            <WinChart :stats="stats" />
            <PlayerTable :stats="stats" />
            <MatchFeed :games="games" />
          </div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style>
/* ── Design tokens ─────────────────────────────────────────────── */
:root {
  --bg:        #060806;
  --surface-1: #0b0f0b;
  --surface-2: #0f140f;
  --border:    #1a2a1a;
  --text:      #c8dcc8;
  --text-dim:  #4a5a4a;
  --green:     #4fe87c;
  --glow-green: 0 0 8px rgba(79,232,124,0.3), 0 0 20px rgba(79,232,124,0.1);
  --red:       #ff5555;
  --glow-red: 0 0 8px rgba(255,85,85,0.3);
  --amber:     #e6b450;
  --glow-amber: 0 0 8px rgba(230,180,80,0.3);
  --font-mono: "SF Mono", "JetBrains Mono", "Fira Code", ui-monospace, Menlo, Consolas, monospace;
  --font-size: 8px;
  --line-h: 1.55;
}
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #020302;
  color: var(--text);
  font: var(--font-size)/var(--line-h) var(--font-mono);
  height: 100vh; overflow: hidden;
}

/* ── Terminal window ───────────────────────────────────────────── */
.terminal {
  width: 100%; height: 100vh;
  background: radial-gradient(ellipse at 50% 0%, rgba(79,232,124,0.03) 0%, transparent 60%), var(--bg);
  display: flex; flex-direction: column; overflow: hidden;
}
.term-titlebar {
  display: flex; align-items: center; gap: 8px;
  padding: 2px 8px;
  border-bottom: 1px solid rgba(79,232,124,0.15);
  font-size: 7px; color: var(--green); flex-shrink: 0; letter-spacing: .08em;
  text-shadow: 0 0 8px rgba(79,232,124,0.5);
}
.tb-title { flex: 1; }
.tb-path { color: var(--text-dim); text-shadow: none; margin-left: 12px; letter-spacing: 0; }
.tb-actions { display: flex; align-items: center; gap: 6px; }
.tb-user { font-size: 7px; color: var(--text-dim); }
.tb-btn { background: none; border: none; color: var(--text-dim); font: 7px var(--font-mono); cursor: pointer; }
.tb-btn:hover { color: var(--text); }
.tb-btn:disabled { opacity: 0.4; }

.term-body { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 4px 8px; }

/* ── Status line ───────────────────────────────────────────────── */
.term-status {
  display: flex; align-items: center; gap: 6px; font-size: 7px; color: var(--text-dim);
  padding-bottom: 5px; border-bottom: 1px solid var(--border); margin-bottom: 5px;
}
.prompt { color: var(--green); }
.spacer { flex: 1; }
.dim { color: var(--text-dim); }
.status-light { width: 5px; height: 5px; border-radius: 50%; background: var(--text-dim); flex-shrink: 0; }
.status-light.ok { background: var(--green); box-shadow: var(--glow-green); }
.status-light.error { background: var(--red); box-shadow: var(--glow-red); }
.status-light.pending { background: var(--amber); box-shadow: var(--glow-amber); animation: pulse 1s ease-in-out infinite; }
.term-select {
  background: var(--surface-2); border: 1px solid var(--border); border-radius: 2px;
  color: var(--text-dim); font: 7px var(--font-mono); padding: 1px 2px; outline: none;
}

.term-content { flex: 1; display: flex; gap: 10px; overflow: hidden; }
.main-content { flex: 1; overflow-y: auto; min-width: 0; }
.main-content::-webkit-scrollbar { width: 3px; }
.main-content::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── ASCII box base ────────────────────────────────────────────── */
.card-box {
  background: var(--surface-1); margin-bottom: 4px; overflow: hidden;
  box-shadow: 0 0 6px rgba(79,232,124,0.04);
  animation: box-expand 0.3s ease backwards;
}
@keyframes box-expand { from { opacity: 0; transform: scaleY(0.8); } to { opacity: 1; transform: scaleY(1); } }
.card-box:nth-child(1) { animation-delay: 0.05s; }
.card-box:nth-child(2) { animation-delay: 0.12s; }
.card-box:nth-child(3) { animation-delay: 0.19s; }
.card-box:nth-child(4) { animation-delay: 0.26s; }

.box-line {
  font-size: 7px; white-space: pre; line-height: 1.2;
  padding: 1px 1ch; overflow: hidden;
}
.box-top { color: rgba(79,232,124,0.5); text-shadow: 0 0 6px rgba(79,232,124,0.3); }
.box-bot { color: rgba(79,232,124,0.5); text-shadow: 0 0 4px rgba(79,232,124,0.2); }
.box-body { color: var(--text-dim); padding: 0 1ch; line-height: 1.6; overflow: hidden; }
.box-body .g { color: var(--green); }
.box-body .r { color: var(--red); }
.box-body .a { color: var(--amber); }
.box-body b { color: var(--text); }
.card-body { font-size: 7px; color: var(--text-dim); padding: 3px 8px; line-height: 1.6; }
.card-body .g { color: var(--green); }
.card-body .r { color: var(--red); }
.card-body .a { color: var(--amber); }
.card-body b { color: var(--text); }

/* ── Terminal animations ─────────────────────────────────────────── */
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
@keyframes glow-in { from { text-shadow: 0 0 0 transparent; } to { text-shadow: 0 0 6px rgba(79,232,124,0.4); } }
@keyframes cursor-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
@keyframes type-in {
  from { opacity: 0; transform: translateY(2px); }
  to { opacity: 1; transform: translateY(0); }
}

.term-content { flex: 1; display: flex; gap: 10px; overflow: hidden; }

/* ── Terminal print-out: staggered type-in on children ──────────── */
.type-block > * { animation: type-in 0.12s ease backwards; }
.type-block > *:nth-child(1) { animation-delay: 0.02s; }
.type-block > *:nth-child(2) { animation-delay: 0.05s; }
.type-block > *:nth-child(3) { animation-delay: 0.08s; }
.type-block > *:nth-child(4) { animation-delay: 0.11s; }
.type-block > *:nth-child(5) { animation-delay: 0.14s; }
.type-block > *:nth-child(6) { animation-delay: 0.17s; }
.type-block > *:nth-child(7) { animation-delay: 0.20s; }
.type-block > *:nth-child(8) { animation-delay: 0.23s; }
.type-block > *:nth-child(9) { animation-delay: 0.26s; }
.type-block > *:nth-child(10) { animation-delay: 0.29s; }

/* Apply type-in to any text-line container */
.cards-enter-active { transition: all 0.2s ease; }
.cards-enter-from { opacity: 0; transform: translateY(3px); }

/* Blinking cursor utility */
.cursor-end::after { content: "█"; color: var(--green); animation: cursor-blink 1s step-end infinite; margin-left: 2px; }

/* Fade transition for route changes */
.fade-enter-active { transition: opacity 0.2s ease; }
.fade-leave-active { transition: opacity 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

</style>
