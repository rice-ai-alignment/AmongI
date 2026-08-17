<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import AsciiTable from "./AsciiTable.vue";
import JobPopup from "./JobPopup.vue";

const { allJobs, watchAllJobs, stopAllJobsWatch } = useFirestore();

onMounted(() => { watchAllJobs(); });
onUnmounted(() => { stopAllJobsWatch(); });

const now = ref(Date.now());
setInterval(() => { now.value = Date.now(); }, 1000);

const showAll = ref(false);
const LIMIT = 10;
const selectedJob = ref(null);

function cleanError(err) {
  if (!err) return "";
  return err.replace(/\s+/g, " ").trim();
}

const columns = [
  { key: "status",  header: "STATUS" },
  { key: "target",  header: "STUDY/EXP" },
  { key: "server",  header: "SERVER" },
  { key: "time",    header: "TIME" },
  { key: "result",  header: "RESULT", align: "right" },
];

function fmtTime(d) {
  if (!d) return null;
  const t = d.toDate ? d.toDate() : new Date(d);
  return t.toLocaleString("sv").replace("T", " ").slice(0, 16);
}

function elapsed(s) {
  if (!s) return null;
  const t = s.toDate ? s.toDate().getTime() : new Date(s).getTime();
  const sec = Math.floor((now.value - t) / 1000);
  let out;
  if (sec < 60) out = `${sec}s`;
  else if (sec < 3600) out = `${Math.floor(sec / 60)}m`;
  else out = `${Math.floor(sec / 3600)}h`;
  // Fixed width so ticking timers never change column/box width
  return out.padStart(5);
}

function trunc(s, n) { return s && s.length > n ? s.slice(0, n) + "…" : s || "-"; }

const statusIcon = { queued: "○", claimed: "◐", running: "●", completed: "✓", failed: "✗", cancelled: "⊘" };
const statusCls  = { queued: "a", claimed: "g", running: "g", completed: "g", failed: "r", cancelled: "r" };

function formatCell(key, val, row) {
  if (key === "status") return { text: `${statusIcon[row._status] || "?"} ${row._status}`, cls: statusCls[row._status] };
  if (key === "target") return { text: trunc(row.study_id, 10) + "/" + trunc(row.experiment_code, 12) };
  if (key === "server") return { text: trunc(row.claimed_by, 14) };
  if (key === "time") {
    if (row._status === "completed" || row._status === "failed") return { text: fmtTime(row.finished_at) };
    if (row.started_at) return { text: elapsed(row.started_at), cls: "g" };
    return { text: elapsed(row.created_at), cls: "dim" };
  }
  if (key === "result") {
    const parts = [];
    const done = row.result?.trials_completed ?? row.result?.games_completed ?? row.result?.games;
    if (done != null) parts.push(done + "t");
    if (row.error) {
      const err = cleanError(row.error);
      return { text: err.slice(0, 60) + (err.length > 60 ? "[...]" : ""), cls: "r" };
    }
    return { text: parts.join(" ") || "-" };
  }
  return { text: String(val ?? "-") };
}

function onJobRowClick(row) {
  if (!row) return;
  selectedJob.value = row;
}

const allRows = computed(() =>
  allJobs.value.map(j => ({
    ...j,
    _status: j.status || "?",
    _fullError: j.error || "",
  }))
);

const activeRows = computed(() => allRows.value.filter(r => ["queued", "claimed", "running"].includes(r._status)));
const historyRows = computed(() => allRows.value.filter(r => ["completed", "failed", "cancelled"].includes(r._status)));
const visibleHistory = computed(() => showAll.value ? historyRows.value : historyRows.value.slice(0, LIMIT));
const hiddenCount = computed(() => Math.max(0, historyRows.value.length - LIMIT));
</script>

<template>
  <div class="all-jobs">
    <AsciiTable
      title="active jobs"
      :columns="columns"
      :rows="activeRows"
      :formatCell="formatCell"
      :minWidth="72"
      :collapsible="false"
      emptyText="(none)"
      :clickableRows="true"
      noType
      @rowClick="onJobRowClick"
    />
    <AsciiTable
      title="job history"
      :columns="columns"
      :rows="visibleHistory"
      :formatCell="formatCell"
      :minWidth="72"
      :collapsible="true"
      emptyText="(none)"
      noType
      :clickableRows="true"
      @rowClick="onJobRowClick"
    />
    <div v-if="hiddenCount" class="dim expand" @click="showAll = !showAll">
      {{ showAll ? '[ collapse ]' : `[ show all (${hiddenCount} more) ]` }}
    </div>

    <JobPopup :job="selectedJob" @close="selectedJob = null" />
  </div>
</template>

<style scoped>
.all-jobs { display: flex; flex-direction: column; }
.expand { font-size: var(--fs-sm); cursor: pointer; padding: var(--sp-xxs) var(--sp-sm); }
.expand:hover { color: var(--green); }
</style>
