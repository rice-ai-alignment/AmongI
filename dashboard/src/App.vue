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
import ConfigCard from "./components/ConfigCard.vue";
import StaggerBlock from "./components/StaggerBlock.vue";
import ServerList from "./components/ServerList.vue";
import AllJobsList from "./components/AllJobsList.vue";
import AdminPanel from "./components/AdminPanel.vue";
import DataViewer from "./components/DataViewer.vue";
import GameInspector from "./components/GameInspector.vue";
import JobStatus from "./components/JobStatus.vue";
import ConfirmPopup from "./components/ConfirmPopup.vue";
import DocsPanel from "./components/DocsPanel.vue";
import TerminalCard from "./components/TerminalCard.vue";
import CopyButton from "./components/CopyButton.vue";
import LandingPage from "./components/LandingPage.vue";

const {
  user, authReady, initAuth, signIn, signOut,
  studies, activeStudyId, loadStudies, studyExperiments, loadAllExperiments,
  experiments, activeExperimentId, loadExperiments,
  stats, games, statusKind, statusText, lastSync, fetchData,
  servers, startServerWatch, stopServerWatch,
  canRunExperiments, isAdmin, loadUserPermissions,
  jobs, watchJobsForExperiment, unwatchJobs, queueJob,
  loadExperimentConfig, saveExperimentConfig, clearExperimentData,
} = useFirestore();

const browsing = ref(true);
const interval = ref(10);
const activeTab = ref("stats");   // "stats" | "config" | "jobs" (sub-tabs under experiments)
// "home" | "experiments" | "documentation" | "servers" | "admin"
const navMode = ref(window.location.pathname === "/" ? "home" : "experiments");
const configJson = ref(null);
const configLoading = ref(false);
const maxGames = computed(() => configJson.value?.trial_count || 1);

// Config is locked once any data exists — only a data clear unlocks it
const configLocked = computed(() => {
  if (!stats.value) return false;
  const hasGames = (stats.value.total_games || 0) > 0;
  const hasTrials = Array.isArray(stats.value.trials) && stats.value.trials.length > 0;
  return hasGames || hasTrials;
});
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
  if (navMode.value === "home") return "~/";
  if (navMode.value === "servers") return "~/servers";
  if (navMode.value === "documentation") return "~/documentation";
  if (navMode.value === "admin") return "~/admin";
  let p = "~/studies";
  if (activeStudyId.value) p += "/" + studyName.value;
  if (activeExperimentId.value) p += "/" + expName.value;
  return p;
});

// True when configJson came from the DB (safe to run).  False when it
// is a sample fallback — running with it would overwrite the real config.
const configFromDb = ref(false);

async function loadConfig() {
  if (!activeExperimentId.value || !activeStudyId.value) return;
  configLoading.value = true;
  try {
    // Try Firestore first, fall back to sample (view-only, unsaved)
    const fromDB = await loadExperimentConfig(activeStudyId.value, activeExperimentId.value);
    if (fromDB) {
      configJson.value = fromDB;
      configFromDb.value = true;
    } else {
      const res = await fetch("/sample_data/example_basic.json");
      if (res.ok) configJson.value = await res.json();
      configFromDb.value = false;
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

const showRunPopup = ref(false);
const runStatus = ref("idle");   // idle | saving | queuing | done | error
const runError = ref("");
const queuedJobId = ref("");

async function openRunPopup() {
  if (!activeStudyId.value || !activeExperimentId.value) return;
  runStatus.value = "idle";
  runError.value = "";
  queuedJobId.value = "";
  showRunPopup.value = true;
}

// ── Shared config compiler (same code as the server pipeline) ──────
let _schema = null;

async function ensureCompiler() {
  if (!_schema) {
    const res = await fetch("/schema.json");
    _schema = await res.json();
  }
  if (!window.validateConfig) {
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "/schema_compiler.js";
      s.onload = resolve;
      s.onerror = () => reject(new Error("config compiler failed to load"));
      document.head.appendChild(s);
    });
  }
}

async function confirmRun() {
  if (!activeStudyId.value || !activeExperimentId.value) return;
  try {
    // The config on the EXPERIMENT DOC is what runs — never write it here.
    // (Auto-saving here used stale in-memory configs and overwrote real ones.)
    const dbConfig = await loadExperimentConfig(
      activeStudyId.value, activeExperimentId.value);
    if (!dbConfig) {
      runStatus.value = "error";
      runError.value =
        "no config saved for this experiment —\n" +
        "open the [ config ] tab, edit, and press [ save ] first";
      return;
    }

    // Validate the DB config BEFORE queueing — errors block the job
    await ensureCompiler();
    const { errors } = window.validateConfig(dbConfig, _schema);
    if (errors.length) {
      runStatus.value = "error";
      runError.value =
        errors.slice(0, 6).join("\n") +
        (errors.length > 6 ? `\n… and ${errors.length - 6} more` : "") +
        "\n\nfix the config in the [ config ] tab — save changes then run again";
      return;
    }

    runStatus.value = "queuing";
    const jobId = await queueJob({
      studyId: activeStudyId.value,
      experimentCode: activeExperimentId.value,
    });
    queuedJobId.value = jobId;
    runStatus.value = "done";
    activeTab.value = "jobs";
    watchJobsForExperiment(activeStudyId.value, activeExperimentId.value);
  } catch (e) {
    runStatus.value = "error";
    runError.value = e.message || String(e);
  }
}

function dismissRunPopup() {
  showRunPopup.value = false;
  runStatus.value = "idle";
  runError.value = "";
}

const showClearPopup = ref(false);
const clearingData = ref(false);
const clearCountdown = ref(3);
const clearReady = ref(false);
let clearTimer = null;

// ── Reset config to an example ─────────────────────────────────────
const showResetPopup = ref(false);
const resetExamples = ref([]);   // [{name, filename}]
const resetting = ref(false);
const resetError = ref("");

async function openResetPopup() {
  showResetPopup.value = true;
  if (resetExamples.value.length) return;
  const files = [
    { name: "basic (crew + imposter, 5 trials)", file: "/sample_data/example_basic.json" },
    { name: "small kill (fast kills)", file: "/sample_data/example_small_kill.json" },
    { name: "timer (short rounds)", file: "/sample_data/example_timer.json" },
  ];
  const loaded = [];
  for (const f of files) {
    try {
      const res = await fetch(f.file);
      if (res.ok) loaded.push({ name: f.name, filename: f.file.split("/").pop(), json: await res.json() });
    } catch (e) { /* skip unavailable */ }
  }
  resetExamples.value = loaded;
}

async function resetToExample(ex) {
  if (!activeStudyId.value || !activeExperimentId.value) return;
  resetting.value = true;
  resetError.value = "";
  try {
    console.log(`[reset] ${ex.filename} → studies/${activeStudyId.value}/experiments/${activeExperimentId.value}`);
    // saveExperimentConfig verifies the write against the server before returning
    await saveExperimentConfig(
      activeStudyId.value, activeExperimentId.value, ex.json);
    configJson.value = ex.json;
    configFromDb.value = true;
    showResetPopup.value = false;
  } catch (e) {
    resetError.value = e.message || String(e);
    console.error("[reset] failed:", e);
  } finally {
    resetting.value = false;
  }
}

watch(showClearPopup, (val) => {
  if (val) {
    clearCountdown.value = 3;
    clearReady.value = false;
    clearTimer = setInterval(() => {
      clearCountdown.value--;
      if (clearCountdown.value <= 0) {
        clearReady.value = true;
        clearInterval(clearTimer);
      }
    }, 1000);
  } else {
    clearInterval(clearTimer);
    clearReady.value = false;
  }
});
async function clearData() {
  if (!activeStudyId.value || !activeExperimentId.value) return;
  clearingData.value = true;
  try {
    await clearExperimentData(activeStudyId.value, activeExperimentId.value);
    stats.value = null;
    games.value = [];
    await fetchData();
  } catch (e) {
    console.error("Clear data failed:", e);
  } finally {
    clearingData.value = false;
    showClearPopup.value = false;
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
  if (navMode.value === "home") {
    window.history.replaceState({}, "", "/");
    return;
  }
  if (navMode.value === "servers") {
    window.history.replaceState({}, "", "/servers");
    return;
  }
  if (navMode.value === "documentation") {
    window.history.replaceState({}, "", "/documentation");
    return;
  }
  if (navMode.value === "admin") {
    window.history.replaceState({}, "", "/admin");
    return;
  }
  let path = "/studies";
  if (activeStudyId.value) {
    path += "/" + (studyName.value || activeStudyId.value);
    if (activeExperimentId.value) {
      path += "/" + (expName.value || activeExperimentId.value);
    }
  }
  window.history.replaceState({}, "", path);
}

watch(navMode, () => syncURL());
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
        <span class="tb-path"><TypedSpan :text="pathText" :speed="TYPE.normal" :key="pathText" /><span class="tb-cursor">_</span></span>
      </span>
      <span class="tb-actions">
        <template v-if="user">
          <span class="tb-user">[ {{ user.displayName }} ]</span>
          <button class="tb-btn" @click="signOut">[ logout ]</button>
        </template>
        <button v-else class="tb-btn" @click="signIn" :disabled="!authReady">login</button>
      </span>
    </div>

    <!-- Terminal body -->
    <div class="term-body">
      <!-- Top-level nav -->
      <div class="top-nav">
        <span class="tab" :class="{ active: navMode === 'home' }" @click="navMode = 'home'">[ home ]</span>
        <span class="tab" :class="{ active: navMode === 'experiments' }" @click="navMode = 'experiments'">[ experiments ]</span>
        <span class="tab" :class="{ active: navMode === 'documentation' }" @click="navMode = 'documentation'">[ documentation ]</span>
        <span class="tab" :class="{ active: navMode === 'servers' }" @click="navMode = 'servers'">[ servers ]</span>
        <span v-if="isAdmin" class="tab" :class="{ active: navMode === 'admin' }" @click="navMode = 'admin'">[ admin ]</span>
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

      <!-- Home view — live stats, same terminal shell -->
      <div class="term-content" v-if="navMode === 'home'" style="flex-direction:column; gap:10px; overflow:hidden;">
        <LandingPage />
      </div>

      <!-- Experiments view -->
      <div class="term-content" v-if="navMode === 'experiments'">
        <StudyBrowser @browsing="browsing = $event" />
        <div class="main-content" v-if="!browsing && activeExperimentId">
          <div class="tab-bar">
            <span class="tab" :class="{ active: activeTab === 'stats' }" @click="switchTab('stats')">[ stats ]</span>
            <span class="tab" :class="{ active: activeTab === 'config' }" @click="switchTab('config')">[ config ]</span>
            <span class="tab" :class="{ active: activeTab === 'jobs' }" @click="switchTab('jobs')">[ jobs ]</span>
            <span class="tab" :class="{ active: activeTab === 'data' }" @click="switchTab('data')">[ data ]</span>
            <span class="tab" :class="{ active: activeTab === 'inspect' }" @click="switchTab('inspect')">[ inspect ]</span>
            <span class="spacer"></span>
            <span v-if="user && activeTab === 'config' && !configLocked" class="tab" @click="openResetPopup">[ reset to example ]</span>
          </div>
          <StaggerBlock v-if="activeTab === 'stats'" :key="'stats-' + activeExperimentId">
            <TilesSection :stats="stats" :config="configJson" />
            <WinChart :stats="stats" :config="configJson" />
            <div class="clear-bar" v-if="user && configLocked">
              <span class="dim">data: {{ stats.total_games }} trials —</span>
              <button class="run-btn" @click="showClearPopup = true" :disabled="clearingData">
                {{ clearingData ? 'clearing...' : '[ clear data ]' }}
              </button>
            </div>
            <PlayerTable :stats="stats" :config="configJson" />
            <MatchFeed :games="games" />
          </StaggerBlock>
          <StaggerBlock v-if="activeTab === 'config'" :key="'config-' + activeExperimentId">
            <div v-if="configLocked" class="lock-bar">
              <span class="a">[ locked ]</span>
              <span class="dim">config is read-only while experiment data exists —</span>
              <button class="run-btn" @click="showClearPopup = true">[ clear data ]</button>
            </div>
            <ConfigCard :config="configJson" title="experiment config" :editable="!configLocked" @saved="configJson = $event; configFromDb = true" @update="configJson = $event" />
          </StaggerBlock>
          <StaggerBlock v-if="activeTab === 'data'" :key="'data-' + activeExperimentId">
            <DataViewer />
          </StaggerBlock>
          <StaggerBlock v-if="activeTab === 'inspect'" :key="'inspect-' + activeExperimentId">
            <GameInspector />
          </StaggerBlock>
          <StaggerBlock v-if="activeTab === 'jobs'" :key="'jobs-' + activeExperimentId">
            <div class="run-bar" v-if="user">
              <span class="dim">{{ maxGames }} trials from config —</span>
              <button v-if="canRunExperiments" class="run-btn" @click="openRunPopup">[ run on server ]</button>
              <span v-else class="dim" title="requires can_run_experiments permission">(no permission)</span>
              <span class="spacer"></span>
              <CopyButton :command="copyCommand" label="copy command" />
            </div>
            <div v-else class="dim" style="margin-bottom:var(--sp-xs)">sign in to run experiments</div>
            <JobStatus />
          </StaggerBlock>
        </div>
      </div>

      <!-- Documentation view -->
      <div class="term-content" v-if="navMode === 'documentation'">
        <DocsPanel />
      </div>

      <!-- Servers view -->
      <div class="term-content" v-if="navMode === 'servers'" style="flex-direction:column; gap:10px;">
        <ServerList />
        <AllJobsList />
      </div>

      <!-- Admin view -->
      <div class="term-content" v-if="navMode === 'admin'">
        <AdminPanel />
      </div>
    </div>
  </div>

  <!-- Run confirmation popup -->
  <div v-if="showRunPopup" class="popup-overlay" @click="dismissRunPopup">
    <div class="popup" @click.stop>
      <TerminalCard title="run experiment" :min-width="36" :collapsible="false">
        <div v-if="runStatus === 'idle' || runStatus === 'saving' || runStatus === 'queuing'">
          <div><span class="dim">study:</span> {{ activeStudyId }}</div>
          <div><span class="dim">experiment:</span> {{ activeExperimentId }}</div>
          <div><span class="dim">games:</span> {{ maxGames }} (from config)</div>
          <div v-if="runStatus === 'saving'" class="a" style="margin-top:var(--sp-sm)">saving config...</div>
          <div v-if="runStatus === 'queuing'" class="a" style="margin-top:var(--sp-sm)">queuing job...</div>
          <div class="popup-acts" style="margin-top:var(--sp-md)">
            <span class="pop-link" @click="dismissRunPopup">[ cancel ]</span>
            <span v-if="runStatus === 'idle'" class="pop-link g" @click="confirmRun">[ run ]</span>
          </div>
        </div>
        <div v-else-if="runStatus === 'done'">
          <div class="g">job queued</div>
          <div class="dim" style="margin-top:var(--sp-xs)">{{ queuedJobId }}</div>
          <div class="dim">switched to jobs tab — monitor progress there</div>
          <div class="popup-acts" style="margin-top:var(--sp-md)">
            <span class="pop-link g" @click="dismissRunPopup">[ ok ]</span>
          </div>
        </div>
        <div v-else-if="runStatus === 'error'">
          <div class="r">failed to queue job</div>
          <div class="dim" style="margin-top:var(--sp-xs); white-space:pre-line; max-height:30vh; overflow-y:auto">{{ runError }}</div>
          <div class="popup-acts" style="margin-top:var(--sp-md)">
            <span class="pop-link" @click="dismissRunPopup">[ close ]</span>
          </div>
        </div>
      </TerminalCard>
    </div>
  </div>

  <!-- Reset config to example popup -->
  <div v-if="showResetPopup" class="popup-overlay" @click="showResetPopup = false">
    <div class="popup" @click.stop>
      <TerminalCard title="reset config" :min-width="40" :collapsible="false">
        <div class="dim">pick a template — overwrites the current config:</div>
        <div v-if="!resetExamples.length" class="dim" style="margin-top:var(--sp-xs)">loading examples...</div>
        <div v-for="ex in resetExamples" :key="ex.filename" class="reset-item" @click="resetToExample(ex)">
          ▸ {{ ex.name }}
        </div>
        <div v-if="resetting" class="a" style="margin-top:var(--sp-xs)">saving...</div>
        <div v-if="resetError" class="r" style="margin-top:var(--sp-xs); white-space:pre-line">{{ resetError }}</div>
        <div class="popup-acts" style="margin-top:var(--sp-md)">
          <span class="pop-link" @click="showResetPopup = false">[ cancel ]</span>
        </div>
      </TerminalCard>
    </div>
  </div>

  <!-- Clear data confirmation popup -->
  <ConfirmPopup
    v-if="showClearPopup"
    :message="'archive all stats & games for ' + (activeStudyId || '?') + '/' + (activeExperimentId || '?') + '?'"
    :buttons="[
      { text: '[ cancel ]', action: 'cancel' },
      { text: clearingData ? 'clearing...' : clearReady ? '[ clear all data ]' : '[ wait ' + clearCountdown + 's ]', action: 'confirm', danger: true },
    ]"
    @action="(act) => {
      if (act === 'confirm' && clearReady && !clearingData) clearData();
      else showClearPopup = false;
    }"
  />
</template>

<style>
/* ── Design tokens ─────────────────────────────────────────────────── */
:root {
  /* Backgrounds */
  --bg-deep:    #020302;
  --bg:         #060806;
  --surface-1:  #0b0f0b;
  --surface-2:  #0f140f;
  --border:     #1a2a1a;

  /* Text */
  --text:       #c8dcc8;
  --text-dim:   #7d947d;

  /* Accent */
  --green:      #4fe87c;
  --red:        #ff5555;
  --amber:      #e6b450;

  /* Typography scale */
  --font-mono:  "SF Mono", "JetBrains Mono", "Fira Code", ui-monospace, Menlo, Consolas, monospace;
  --fs-xs:      10px;
  --fs-sm:      13px;
  --fs-md:      14px;
  --fs-base:    16px;
  --fs-ui:      18px;
  --fs-lg:      22px;

  /* Line-height scale */
  --lh-tight:   1.2;
  --lh-base:    1.3;
  --lh-body:    1.45;
  --lh-card:    1.55;
  --lh-loose:   1.6;

  /* Spacing scale */
  --sp-xxs:     2px;
  --sp-xs:      4px;
  --sp-sm:      6px;
  --sp-md:      8px;
  --sp-lg:      12px;
  --sp-xl:      14px;

  /* Borders & radius */
  --radius-sm:  2px;
  --border-hair: 1px solid rgba(79,232,124,0.10);
  --border-subtle: 1px solid rgba(79,232,124,0.15);
  --border-panel:  1px solid var(--border);
  --border-accent: 1px solid var(--green);

  /* Glows — green at key alphas */
  --glow-subtle: 0 0 4px  rgba(79,232,124,0.15);
  --glow-soft:   0 0 6px  rgba(79,232,124,0.30);
  --glow-medium: 0 0 8px  rgba(79,232,124,0.40);
  --glow-strong: 0 0 12px rgba(79,232,124,0.50);
  --glow-red:    0 0 8px  rgba(255,85,85,0.30);
  --glow-amber:  0 0 8px  rgba(230,180,80,0.30);

  /* Scrollbar */
  --scrollbar-w: 3px;

  /* ConfigTree depth colors */
  --ct-d0:   #f07070;
  --ct-d1:   #f0a060;
  --ct-d2:   #e0d060;
  --ct-d3:   #60d860;
  --ct-d4:   #60c0c0;
  --ct-d5:   #6098e0;
  --ct-d6:   #a060e0;
  --ct-var:  #60d860;
  --ct-fn:   #e0d060;
  --ct-op:   #80e880;
  --ct-warn: #f0a060;
  --ct-err:  #f07070;
  --ct-lit:  #90a090;
  --ct-num:  #e0d060;
}

/* ── Reset ──────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg-deep);
  color: var(--text);
  font: var(--fs-lg)/var(--lh-base) var(--font-mono);
  height: 100vh; overflow: hidden;
}

/* ── Utility classes ────────────────────────────────────────────────── */
.dim    { color: var(--text-dim); }
.spacer { flex: 1; }
.g, .col-green  { color: var(--green); }
.r, .col-red    { color: var(--red); }
.a, .col-amber  { color: var(--amber); }
.n { color: inherit; }

/* ── Terminal window ────────────────────────────────────────────────── */
.terminal {
  width: 100%; height: 100vh;
  background: radial-gradient(ellipse at 50% 0%, rgba(79,232,124,0.03) 0%, transparent 60%), var(--bg);
  display: flex; flex-direction: column; overflow: hidden;
}
.term-titlebar {
  display: flex; align-items: center; gap: var(--sp-md);
  padding: var(--sp-xxs) var(--sp-md);
  border-bottom: var(--border-subtle);
  font-size: var(--fs-ui); color: var(--green); flex-shrink: 0; letter-spacing: .08em;
  text-shadow: var(--glow-strong);
}
.tb-title  { flex: 1; }
.tb-path    { color: var(--text-dim); text-shadow: none; margin-left: var(--sp-lg); letter-spacing: 0; }
.tb-cursor  { color: var(--green); text-shadow: none; animation: tb-blink 1s step-end infinite; }
@keyframes tb-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
.tb-actions { display: flex; align-items: center; gap: var(--sp-sm); }
.tb-user    { font-size: var(--fs-ui); color: var(--text-dim); }
.tb-btn {
  background: none; border: none; color: var(--text-dim);
  font: var(--fs-ui) var(--font-mono); cursor: pointer;
}
.tb-btn:hover     { color: var(--text); }
.tb-btn:disabled  { opacity: 0.4; }

.term-body {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  padding: var(--sp-xs) var(--sp-md);
}
.term-content {
  flex: 1; display: flex; gap: 10px; overflow-x: hidden; overflow-y: auto; flex-wrap: nowrap;
}

/* ── Status line ────────────────────────────────────────────────────── */
.term-status {
  display: flex; align-items: center; gap: var(--sp-sm);
  font-size: var(--fs-ui); color: var(--text-dim);
  padding-bottom: 5px; border-bottom: var(--border-panel); margin-bottom: 5px;
}
.status-light {
  width: 5px; height: 5px; border-radius: 50%; background: var(--text-dim); flex-shrink: 0;
}
.status-light.ok      { background: var(--green); box-shadow: var(--glow-soft); }
.status-light.error   { background: var(--red);   box-shadow: var(--glow-red); }
.status-light.pending { background: var(--amber); box-shadow: var(--glow-amber); animation: pulse 1s ease-in-out infinite; }
.term-select {
  background: var(--surface-2); border: var(--border-panel); border-radius: var(--radius-sm);
  color: var(--text-dim); font: var(--fs-ui) var(--font-mono); padding: 1px var(--sp-xxs); outline: none;
}

/* ── Main content scrollbar ─────────────────────────────────────────── */
.main-content {
  flex: 1; overflow-y: auto; min-width: 0; display: flex; flex-direction: column;
}
.main-content::-webkit-scrollbar       { width: var(--scrollbar-w); }
.main-content::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }

/* ── Card alt (non-box headers, etc.) ───────────────────────────────── */
.card-head {
  font-size: var(--fs-ui); color: rgba(79,232,124,0.7);
  text-transform: uppercase; letter-spacing: .06em; text-shadow: var(--glow-soft);
  padding: 3px var(--sp-md) var(--sp-xxs);
  border-bottom: 1px solid rgba(79,232,124,0.12);
}
.card-body {
  font-size: var(--fs-ui); color: var(--text-dim);
  padding: 3px var(--sp-md); line-height: var(--lh-loose);
}
.card-body b { color: var(--text); }

/* ── ConfigTree depth colors (use token vars) ──────────────────────── */
.c-d0   { color: var(--ct-d0); }
.c-d1   { color: var(--ct-d1); }
.c-d2   { color: var(--ct-d2); }
.c-d3   { color: var(--ct-d3); }
.c-d4   { color: var(--ct-d4); }
.c-d5   { color: var(--ct-d5); }
.c-d6   { color: var(--ct-d6); }
.c-var  { color: var(--ct-var); }
.c-fn   { color: var(--ct-fn); }
.c-op   { color: var(--ct-op); }
.c-warn { color: var(--ct-warn); }
.c-err  { color: var(--ct-err); }
.c-lit  { color: var(--ct-lit); }
.c-num  { color: var(--ct-num); }

/* ── Layout helpers ──────────────────────────────────────────────────── */

/* ── Nav & tabs ─────────────────────────────────────────────────────── */
.top-nav {
  display: flex; gap: var(--sp-xl); padding: var(--sp-xxs) 0 var(--sp-xs);
  margin-bottom: 5px; border-bottom: var(--border-hair); flex-shrink: 0;
}
.tab-bar {
  display: flex; gap: var(--sp-xl); padding: var(--sp-xxs) 0 var(--sp-xs);
  margin-bottom: var(--sp-xs); border-bottom: var(--border-hair); flex-shrink: 0;
}
.tab {
  font-size: var(--fs-sm); color: var(--text-dim); cursor: pointer;
}
.tab:hover        { color: var(--text); }
.tab.active       { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }

/* ── Clear data bar ────────────────────────────────────────────────────── */
.clear-bar {
  display: flex; align-items: center; gap: var(--sp-sm);
  padding: var(--sp-xs) var(--sp-md); margin-bottom: var(--sp-xs);
}

/* ── Config lock bar ──────────────────────────────────────────────────── */
.lock-bar {
  display: flex; align-items: center; gap: var(--sp-sm);
  padding: var(--sp-xs) var(--sp-md); margin-bottom: var(--sp-xs);
}

/* ── Run bar ──────────────────────────────────────────────────────────── */
.run-bar {
  display: flex; align-items: center; gap: var(--sp-sm);
  padding: var(--sp-xs) var(--sp-md); margin-bottom: var(--sp-xs);
}
.run-btn {
  background: none; border: none;
  color: var(--green); font: var(--fs-md) var(--font-mono);
  padding: 0; cursor: pointer;
  text-shadow: 0 0 5px rgba(79,232,124,0.3);
}
.run-btn:hover { text-shadow: 0 0 8px rgba(79,232,124,0.5); }
.term-inp {
  background: var(--surface-2); border: var(--border-panel); border-radius: var(--radius-sm);
  color: var(--text); font: var(--fs-md) var(--font-mono);
  padding: 1px var(--sp-xs); width: 42px; outline: none;
}

/* ── Box label (standalone green header) ─────────────────────────────── */
.box-label {
  font-size: var(--fs-ui); color: var(--green);
  text-shadow: var(--glow-medium); margin-bottom: var(--sp-sm);
  animation: glow-in 0.5s ease;
}

/* ── Animations ──────────────────────────────────────────────────────── */
@keyframes pulse     { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
@keyframes glow-in   { from { text-shadow: 0 0 0 transparent; } to { text-shadow: var(--glow-medium); } }
@keyframes cursor-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
@keyframes type-in {
  from { opacity: 0; transform: translateY(2px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Transitions ─────────────────────────────────────────────────────── */
.cards-enter-active { transition: all 0.2s ease; }
.cards-enter-from   { opacity: 0; transform: translateY(3px); }
.fade-enter-active  { transition: opacity 0.2s ease; }
.fade-leave-active  { transition: opacity 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* Popup overlay */
.popup-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.popup-acts { display: flex; gap: var(--sp-xl); justify-content: center; }
.pop-link { color: var(--text-dim); cursor: pointer; font-size: var(--fs-ui); }
.pop-link:hover { color: var(--text); }
.pop-link.g:hover { color: var(--green); text-shadow: var(--glow-soft); }
.pop-link.r:hover { color: var(--red); text-shadow: var(--glow-red); }
.reset-item {
  color: var(--text-dim); cursor: pointer; font-size: var(--fs-base);
  padding: var(--sp-xxs) 0; border-bottom: var(--border-hair);
}
.reset-item:hover { color: var(--green); }

/* Blinking cursor utility */
.cursor-end::after {
  content: "█"; color: var(--green);
  animation: cursor-blink 1s step-end infinite; margin-left: var(--sp-xxs);
}
</style>
