<script setup>
import { ref, computed, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";

const { jobs } = useFirestore();

const now = ref(Date.now());
const tick = setInterval(() => { now.value = Date.now(); }, 1000);
onUnmounted(() => clearInterval(tick));

const activeJobs = computed(() =>
  jobs.value.filter(j => j.status === "queued" || j.status === "claimed" || j.status === "running")
);
const historyJobs = computed(() =>
  jobs.value.filter(j => j.status === "completed" || j.status === "failed" || j.status === "cancelled")
);

function fmtTime(d) {
  if (!d) return "-";
  const t = d.toDate ? d.toDate() : new Date(d);
  return t.toLocaleString("sv").replace("T", " ").slice(0, 19);
}

function elapsed(started) {
  if (!started) return "";
  const t = started.toDate ? started.toDate().getTime() : new Date(started).getTime();
  const sec = Math.floor((now.value - t) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
}

function statusClass(s) {
  if (s === "queued") return "a";
  if (s === "claimed" || s === "running") return "g";
  if (s === "completed") return "";
  if (s === "failed" || s === "cancelled") return "r";
  return "dim";
}

function statusIcon(s) {
  if (s === "queued") return "○";
  if (s === "claimed") return "◐";
  if (s === "running") return "●";
  if (s === "completed") return "✓";
  if (s === "failed") return "✗";
  if (s === "cancelled") return "⊘";
  return "?";
}

function resultSummary(r) {
  if (!r) return "";
  const parts = [];
  if (r.games) parts.push(`${r.games} games`);
  if (r.total_kills) parts.push(`${r.total_kills} kills`);
  if (r.by_winner) {
    const w = Object.entries(r.by_winner).map(([k, v]) => `${k}:${v}`).join(", ");
    parts.push(`[${w}]`);
  }
  return parts.join("  ");
}
</script>

<template>
  <div class="jobs-view">
    <!-- Active / Queued jobs -->
    <TerminalCard title="active jobs" :min-width="80" :collapsible="false">
      <div v-if="!activeJobs.length" class="dim">
        (no active jobs — queue one with [ run on server ])
      </div>
      <div v-for="j in activeJobs" :key="j.id" class="job-card">
        <div class="job-header">
          <span :class="statusClass(j.status)">{{ statusIcon(j.status) }} {{ j.status }}</span>
          <span class="dim">{{ j.study_id }}/{{ j.experiment_code }}</span>
          <span class="spacer"></span>
          <span v-if="j.started_at" class="g">{{ elapsed(j.started_at) }}</span>
          <span v-else class="dim">queued {{ elapsed(j.created_at) }} ago</span>
        </div>
        <div class="job-detail dim">
          <span v-if="j.claimed_by">server: {{ j.claimed_by }}</span>
          <span v-if="j.started_at">started: {{ fmtTime(j.started_at) }}</span>
          <span>max games: {{ j.max_games || 1 }}</span>
        </div>
        <div v-if="j.result" class="job-result g">
          {{ resultSummary(j.result) }}
        </div>
      </div>
    </TerminalCard>

    <!-- Job history -->
    <TerminalCard title="job history" :min-width="80" :collapsible="true">
      <div v-if="!historyJobs.length" class="dim">
        (no completed jobs yet)
      </div>
      <div v-for="j in historyJobs" :key="j.id" class="job-card">
        <div class="job-header">
          <span :class="statusClass(j.status)">{{ statusIcon(j.status) }} {{ j.status }}</span>
          <span class="dim">{{ j.study_id }}/{{ j.experiment_code }}</span>
          <span class="spacer"></span>
          <span class="dim">{{ fmtTime(j.finished_at) }}</span>
        </div>
        <div class="job-detail dim">
          <span v-if="j.claimed_by">server: {{ j.claimed_by }}</span>
          <span>created: {{ fmtTime(j.created_at) }}</span>
          <span>games: {{ j.max_games || 1 }}</span>
        </div>
        <div v-if="j.result" class="job-result g">
          {{ resultSummary(j.result) }}
        </div>
        <div v-if="j.error" class="job-error r">{{ j.error }}</div>
      </div>
    </TerminalCard>
  </div>
</template>

<style scoped>
.jobs-view { flex: 1; display: flex; flex-direction: column; gap: var(--sp-sm); }

.job-card {
  padding: var(--sp-xxs) 0;
  border-bottom: var(--border-hair);
}
.job-card:last-child { border-bottom: none; }

.job-header {
  display: flex; align-items: baseline; gap: var(--sp-sm);
  font-size: var(--fs-ui);
}
.job-detail {
  display: flex; gap: var(--sp-lg); font-size: var(--fs-sm);
  padding: var(--sp-xxs) 0 0 var(--sp-sm);
}
.job-result {
  font-size: var(--fs-sm); padding: var(--sp-xxs) 0 0 var(--sp-sm);
}
.job-error {
  font-size: var(--fs-sm); padding: var(--sp-xxs) 0 0 var(--sp-sm);
  max-width: 80ch; word-break: break-word;
}
</style>
