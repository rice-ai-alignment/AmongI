<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";

const { allJobs, watchAllJobs, stopAllJobsWatch } = useFirestore();

onMounted(() => { watchAllJobs(); });
onUnmounted(() => { stopAllJobsWatch(); });

const now = ref(Date.now());
const tick = setInterval(() => { now.value = Date.now(); }, 1000);
onUnmounted(() => clearInterval(tick));

const showAllHistory = ref(false);
const INITIAL = 10;

const activeJobs = computed(() =>
  allJobs.value.filter(j => ["queued", "claimed", "running"].includes(j.status))
);
const allHistory = computed(() =>
  allJobs.value.filter(j => ["completed", "failed", "cancelled"].includes(j.status))
);
const visibleHistory = computed(() =>
  showAllHistory.value ? allHistory.value : allHistory.value.slice(0, INITIAL)
);
const hiddenCount = computed(() =>
  Math.max(0, allHistory.value.length - INITIAL)
);

function fmtTime(d) {
  if (!d) return "-";
  const t = d.toDate ? d.toDate() : new Date(d);
  return t.toLocaleString("sv").replace("T", " ").slice(0, 16);
}

function elapsed(started) {
  if (!started) return "";
  const t = started.toDate ? started.toDate().getTime() : new Date(started).getTime();
  const sec = Math.floor((now.value - t) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h`;
}

function statusClass(s) {
  return { queued: "a", claimed: "g", running: "g", completed: "", failed: "r", cancelled: "r" }[s] || "dim";
}

function statusIcon(s) {
  return { queued: "○", claimed: "◐", running: "●", completed: "✓", failed: "✗", cancelled: "⊘" }[s] || "?";
}

function trunc(s, n) {
  if (!s) return "-";
  return s.length > n ? s.slice(0, n) + "..." : s;
}
</script>

<template>
  <div class="all-jobs">
    <TerminalCard title="active jobs" :min-width="80" :collapsible="false">
      <div v-if="!activeJobs.length" class="dim">(none)</div>
      <div v-for="j in activeJobs" :key="j.id" class="job-row">
        <span :class="statusClass(j.status)" class="j-status">{{ statusIcon(j.status) }} {{ j.status }}</span>
        <span class="dim j-study">{{ trunc(j.study_id, 12) }}/{{ trunc(j.experiment_code, 14) }}</span>
        <span class="spacer"></span>
        <span v-if="j.claimed_by" class="dim j-server">{{ trunc(j.claimed_by, 14) }}</span>
        <span v-if="j.started_at" class="g j-time">{{ elapsed(j.started_at) }}</span>
        <span v-else class="dim j-time">{{ elapsed(j.created_at) }}</span>
      </div>
    </TerminalCard>

    <TerminalCard title="job history" :min-width="80" :collapsible="true">
      <div v-if="!allHistory.length" class="dim">(none)</div>
      <div v-for="j in visibleHistory" :key="j.id" class="job-row">
        <span :class="statusClass(j.status)" class="j-status">{{ statusIcon(j.status) }} {{ j.status }}</span>
        <span class="dim j-study">{{ trunc(j.study_id, 12) }}/{{ trunc(j.experiment_code, 14) }}</span>
        <span class="spacer"></span>
        <span v-if="j.claimed_by" class="dim j-server">{{ trunc(j.claimed_by, 14) }}</span>
        <span class="dim j-time">{{ fmtTime(j.finished_at) }}</span>
        <span v-if="j.result?.games" class="dim">· {{ j.result.games }}g</span>
        <span v-if="j.error" class="r j-err">· {{ j.error.slice(0, 50) }}</span>
      </div>
      <div v-if="hiddenCount" class="expand-row dim" @click="showAllHistory = !showAllHistory">
        {{ showAllHistory ? '[ collapse ]' : `[ show all (${hiddenCount} more) ]` }}
      </div>
    </TerminalCard>
  </div>
</template>

<style scoped>
.all-jobs { display: flex; flex-direction: column; gap: var(--sp-sm); }
.job-row {
  display: flex; align-items: baseline; gap: var(--sp-sm);
  font-size: var(--fs-base); padding: var(--sp-xxs) 0;
  border-bottom: var(--border-hair); overflow: hidden;
}
.job-row:last-child { border-bottom: none; }
.j-status { flex-shrink: 0; width: 10ch; }
.j-study  { flex-shrink: 0; width: 28ch; overflow: hidden; white-space: nowrap; }
.j-server { flex-shrink: 0; width: 16ch; overflow: hidden; white-space: nowrap; }
.j-time   { flex-shrink: 0; width: 16ch; }
.j-err    { flex-shrink: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; min-width: 0; }
.expand-row {
  font-size: var(--fs-sm); cursor: pointer; padding-top: var(--sp-xxs);
}
.expand-row:hover { color: var(--green); }
</style>
