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
import ConfigViewer from "./components/ConfigViewer.vue";
import ConfigTree from "./components/ConfigTree.vue";
import StaggerBlock from "./components/StaggerBlock.vue";
import ServerList from "./components/ServerList.vue";
import JobStatus from "./components/JobStatus.vue";
import CopyButton from "./components/CopyButton.vue";

const {
  user, authReady, initAuth, signIn, signOut,
  studies, activeStudyId, loadStudies, studyExperiments, loadAllExperiments,
  experiments, activeExperimentId, loadExperiments,
  stats, games, statusKind, statusText, lastSync, fetchData,
  servers, startServerWatch, stopServerWatch,
  canRunExperiments, loadUserPermissions,
  jobs, watchJobsForExperiment, unwatchJobs, queueJob,
  loadExperimentConfig,
} = useFirestore();

const browsing = ref(true);
const interval = ref(10);
const activeTab = ref("stats");   // "stats" | "config" | "jobs" (sub-tabs under experiments)
const navMode = ref("experiments"); // "experiments" | "database" | "servers"
const configJson = ref(null);
const configLoading = ref(false);
const maxGames = ref(1);
let pollTimer = null;

// Copy command for manual runs
const copyCommand = computed(() => {
  const study = activeStudyId.value || "S";
  const exp = activeExperimentId.value || "E";
  return `python run.py --config-firestore --firebase --study ${study} --experiment ${exp}`;
});

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

async function loadConfig() {
  if (!activeExperimentId.value || !activeStudyId.value) return;
  configLoading.value = true;
  try {
    // Try Firestore first, fall back to sample
    const fromDB = await loadExperimentConfig(activeStudyId.value, activeExperimentId.value);
    if (fromDB) {
      configJson.value = fromDB;
    } else {
      const res = await fetch("/sample_data/example_basic.json");
      if (res.ok) configJson.value = await res.json();
    }
  } catch (e) {
    console.error("Failed to load config:", e);
  } finally {
    configLoading.value = false;
  }
}

function switchTab(tab) {
  activeTab.value = tab;
  if (tab === "config" && !configJson.value) loadConfig();
  if (tab === "jobs" && activeStudyId.value && activeExperimentId.value) {
    watchJobsForExperiment(activeStudyId.value, activeExperimentId.value);
  }
}

async function runExperiment() {
  if (!activeStudyId.value || !activeExperimentId.value) return;
  try {
    // Ensure config is loaded
    if (!configJson.value) await loadConfig();
    await queueJob({
      studyId: activeStudyId.value,
      experimentCode: activeExperimentId.value,
      config: configJson.value || {},
      maxGames: maxGames.value,
    });
    // Switch to jobs tab to show status
    activeTab.value = "jobs";
    watchJobsForExperiment(activeStudyId.value, activeExperimentId.value);
  } catch (e) {
    console.error("Failed to queue job:", e);
  }
}

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
  const u = await initAuth();
  if (u) loadUserPermissions(u.uid);
  await loadStudies();
  await loadAllExperiments();
  restartPolling();
  startServerWatch();

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
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer);
  stopServerWatch();
  unwatchJobs();
});
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
      <!-- Top-level nav -->
      <div class="top-nav">
        <span class="tab" :class="{ active: navMode === 'experiments' }" @click="navMode = 'experiments'">[ experiments ]</span>
        <span class="tab" :class="{ active: navMode === 'database' }" @click="navMode = 'database'">[ database ]</span>
        <span class="tab" :class="{ active: navMode === 'servers' }" @click="navMode = 'servers'">[ servers ]</span>
      </div>

      <!-- Status line (experiments only) -->
      <div class="term-status" v-if="navMode === 'experiments'">
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

      <!-- Experiments view -->
      <div class="term-content" v-if="navMode === 'experiments'">
        <StudyBrowser @browsing="browsing = $event" />
        <div class="main-content" v-if="!browsing && activeExperimentId">
          <div class="tab-bar">
            <span class="tab" :class="{ active: activeTab === 'stats' }" @click="switchTab('stats')">[ stats ]</span>
            <span class="tab" :class="{ active: activeTab === 'config' }" @click="switchTab('config')">[ config ]</span>
            <span class="tab" :class="{ active: activeTab === 'jobs' }" @click="switchTab('jobs')">[ jobs ]</span>
          </div>
          <StaggerBlock v-if="activeTab === 'stats'" :key="'stats-' + activeExperimentId">
            <TilesSection :stats="stats" />
            <WinChart :stats="stats" />
            <PlayerTable :stats="stats" />
            <MatchFeed :games="games" />
            <!-- Run experiment -->
            <div class="run-bar" v-if="user">
              <span class="dim">run:</span>
              <input v-model.number="maxGames" type="number" min="1" max="50" class="term-inp" />
              <span class="dim">games</span>
              <button v-if="canRunExperiments" class="run-btn" @click="runExperiment">[ run on server ]</button>
              <span v-else class="dim" title="requires can_run_experiments permission">(no permission)</span>
              <span class="spacer"></span>
              <CopyButton :command="copyCommand" label="copy command" />
            </div>
          </StaggerBlock>
          <StaggerBlock v-if="activeTab === 'config'" :key="'config-' + activeExperimentId">
            <ConfigTree :config="configJson" title="experiment config" />
            <ConfigViewer />
          </StaggerBlock>
          <StaggerBlock v-if="activeTab === 'jobs'" :key="'jobs-' + activeExperimentId">
            <JobStatus />
          </StaggerBlock>
        </div>
      </div>

      <!-- Database view (standalone) -->
      <ConfigViewer v-if="navMode === 'database'" />

      <!-- Servers view -->
      <div class="term-content" v-if="navMode === 'servers'">
        <ServerList />
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
  --border-solid: #4fe87c;
  --glow-green: 0 0 8px rgba(79,232,124,0.3), 0 0 20px rgba(79,232,124,0.1);
  --red:       #ff5555;
  --glow-red: 0 0 8px rgba(255,85,85,0.3);
  --amber:     #e6b450;
  --glow-amber: 0 0 8px rgba(230,180,80,0.3);
  --font-mono: "SF Mono", "JetBrains Mono", "Fira Code", ui-monospace, Menlo, Consolas, monospace;
  --font-size: 22px;
  --line-h: 1.3;
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
  font-size: 18px; color: var(--green); flex-shrink: 0; letter-spacing: .08em;
  text-shadow: 0 0 8px rgba(79,232,124,0.5);
}
.tb-title { flex: 1; }
.tb-path { color: var(--text-dim); text-shadow: none; margin-left: 12px; letter-spacing: 0; }
.tb-actions { display: flex; align-items: center; gap: 6px; }
.tb-user { font-size: 18px; color: var(--text-dim); }
.tb-btn { background: none; border: none; color: var(--text-dim); font: 18px var(--font-mono); cursor: pointer; }
.tb-btn:hover { color: var(--text); }
.tb-btn:disabled { opacity: 0.4; }

.term-body { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 4px 8px; }
.term-content { flex: 1; display: flex; gap: 10px; overflow: hidden; flex-wrap: nowrap; }

/* ── Status line ───────────────────────────────────────────────── */
.term-status {
  display: flex; align-items: center; gap: 6px; font-size: 18px; color: var(--text-dim);
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
  color: var(--text-dim); font: 18px var(--font-mono); padding: 1px 2px; outline: none;
}

.main-content { flex: 1; overflow-y: auto; min-width: 0; display: flex; flex-direction: column; }
.main-content::-webkit-scrollbar { width: 3px; }
.main-content::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── ASCII box base ────────────────────────────────────────────── */
.card-box {
  background: var(--surface-1); margin-bottom: 4px; overflow: hidden;
  box-shadow: 0 0 6px rgba(79,232,124,0.06), inset 0 0 4px rgba(79,232,124,0.03);
  animation: box-expand 0.3s ease backwards;
}
@keyframes box-expand { from { opacity: 0; transform: scaleY(0.8); } to { opacity: 1; transform: scaleY(1); } }
.card-box:nth-child(1) { animation-delay: 0.05s; }
.card-box:nth-child(2) { animation-delay: 0.12s; }
.card-box:nth-child(3) { animation-delay: 0.19s; }
.card-box:nth-child(4) { animation-delay: 0.26s; }

.box-line {
  font-size: 18px; white-space: pre; line-height: 1.2;
  padding: 2px 8px; overflow: hidden;
}
.box-top { color: var(--border-solid); text-shadow: 0 0 6px rgba(79,232,124,0.4); }
.box-bot { color: var(--border-solid); text-shadow: 0 0 4px rgba(79,232,124,0.3); }
.box-body { color: var(--text-dim); padding: 0 6px 0 calc(6px + 1ch); line-height: 1.6; overflow: hidden; white-space: pre; }
.box-body .g, .col-green { color: var(--green); }
.box-body .r, .col-red { color: var(--red); }
.box-body .a, .col-amber { color: var(--amber); }
.box-body .n { color: inherit; }
.box-body b { color: var(--text); }

/* ── ConfigTree depth colors ─────────────────────────────────── */
.c-d0 { color: #f07070; }
.c-d1 { color: #f0a060; }
.c-d2 { color: #e0d060; }
.c-d3 { color: #60d860; }
.c-d4 { color: #60c0c0; }
.c-d5 { color: #6098e0; }
.c-d6 { color: #a060e0; }
.c-var  { color: #60d860; }
.c-fn   { color: #e0d060; }
.c-op   { color: #80e880; }
.c-warn { color: #f0a060; }
.c-err  { color: #f07070; }
.c-lit  { color: #90a090; }
.c-num  { color: #e0d060; }
.tbl-row { display: flex; gap: 8px; overflow: hidden; }
.tbl-row > * { flex-shrink: 0; white-space: pre; }
.card-head { font-size: 18px; color: rgba(79,232,124,0.7); text-transform: uppercase; letter-spacing: .06em; text-shadow: 0 0 6px rgba(79,232,124,0.3); padding: 3px 8px 2px; border-bottom: 1px solid rgba(79,232,124,0.12); }
.card-body { font-size: 18px; color: var(--text-dim); padding: 3px 8px; line-height: 1.6; }
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

.top-nav { display: flex; gap: 14px; padding: 2px 0 4px; margin-bottom: 5px; border-bottom: 1px solid rgba(79,232,124,0.1); flex-shrink: 0; }
.tab-bar { display: flex; gap: 14px; padding: 2px 0 4px; margin-bottom: 4px; border-bottom: 1px solid rgba(79,232,124,0.1); flex-shrink: 0; }
.tab { font-size: 13px; color: var(--text-dim); cursor: pointer; }
.tab:hover { color: var(--text); }
.tab.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }

/* ── Terminal print-out: staggered type-in on children ──────────── */
/* (use <StaggerBlock> component — .type-block rules moved there) */

/* Apply type-in to any text-line container */
.run-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; margin-bottom: 4px;
}
.run-btn {
  background: none; border: 1px solid var(--green); border-radius: 2px;
  color: var(--green); font: 14px var(--font-mono); padding: 1px 6px; cursor: pointer;
  text-shadow: 0 0 5px rgba(79,232,124,0.3);
}
.run-btn:hover { background: rgba(79,232,124,0.1); }
.term-inp {
  background: var(--surface-2); border: 1px solid var(--border); border-radius: 2px;
  color: var(--text); font: 14px var(--font-mono); padding: 1px 4px; width: 42px;
  outline: none;
}

.cards-enter-active { transition: all 0.2s ease; }
.cards-enter-from { opacity: 0; transform: translateY(3px); }

/* Blinking cursor utility */
.cursor-end::after { content: "█"; color: var(--green); animation: cursor-blink 1s step-end infinite; margin-left: 2px; }

/* Fade transition for route changes */
.fade-enter-active { transition: opacity 0.2s ease; }
.fade-leave-active { transition: opacity 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

</style>
