<script setup>
import { ref, computed, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import AsciiTable from "./AsciiTable.vue";
import JobPopup from "./JobPopup.vue";

const { jobs } = useFirestore();

const now = ref(Date.now());
const tick = setInterval(() => { now.value = Date.now(); }, 1000);
onUnmounted(() => clearInterval(tick));

const showAll = ref(false);
const LIMIT = 10;
const selectedJob = ref(null);

function cleanError(err) {
  if (!err) return "";
  return err.replace(/\s+/g, " ").trim();
}

const columns = [
  { key: "status",  header: "STATUS" },
  { key: "created", header: "CREATED" },
  { key: "server",  header: "SERVER" },
  { key: "games",   header: "TRIALS", align: "right" },
  { key: "result",  header: "RESULT" },
];

function fmtTime(d) {
  if (!d) return "-";
  const t = d.toDate ? d.toDate() : new Date(d);
  return t.toLocaleString("sv").replace("T", " ").slice(0, 16);
}

function elapsed(s) {
  if (!s) return "-".padEnd(6);
  const t = s.toDate ? s.toDate().getTime() : new Date(s).getTime();
  const sec = Math.floor((now.value - t) / 1000);
  let out;
  if (sec < 60) out = `${sec}s`;
  else if (sec < 3600) out = `${Math.floor(sec / 60)}m ${sec % 60}s`;
  else out = `${Math.floor(sec / 3600)}h`;
  // Fixed width so ticking timers never change column/box width
  return out.padStart(6);
}

const statusIcon = { queued: "○", claimed: "◐", running: "●", completed: "✓", failed: "✗", cancelled: "⊘" };
const statusCls  = { queued: "a", claimed: "g", running: "g", completed: "g", failed: "r", cancelled: "r" };

function formatCell(key, val, row) {
  if (key === "status") return { text: `${statusIcon[row._status] || "?"} ${row._status}`, cls: statusCls[row._status] };
  if (key === "created") return { text: fmtTime(row.created_at) };
  if (key === "server") return { text: row.claimed_by || "-" };
  if (key === "games") {
    const done = row.result?.trials_completed ?? row.result?.games_completed;
    const total = row.result?.trial_count ?? row.max_games;
    if (done != null && total != null) return { text: `${done}/${total}` };
    if (done != null) return { text: String(done) };
    return { text: "-" };
  }
  if (key === "result") {
    if (row._status === "running" && row.started_at) return { text: elapsed(row.started_at), cls: "g" };
    if (row._status === "completed") return { text: fmtTime(row.finished_at) };
    if (row._status === "failed") {
      const err = cleanError(row._fullError || row.error || "");
      return { text: err.slice(0, 60) + (err.length > 60 ? "[...]" : ""), cls: "r" };
    }
    if (row._status === "queued") return { text: elapsed(row.created_at), cls: "dim" };
    return { text: "-" };
  }
  return { text: String(val ?? "-") };
}

function onJobRowClick(row) {
  if (!row) return;
  selectedJob.value = row;
}

const allRows = computed(() =>
  jobs.value.map(j => ({ ...j, _status: j.status || "?", _fullError: j.error || "" }))
);
const activeRows = computed(() => allRows.value.filter(r => ["queued", "claimed", "running"].includes(r._status)));
const historyRows = computed(() => allRows.value.filter(r => ["completed", "failed", "cancelled"].includes(r._status)));
const visibleHistory = computed(() => showAll.value ? historyRows.value : historyRows.value.slice(0, LIMIT));
const hiddenCount = computed(() => Math.max(0, historyRows.value.length - LIMIT));
</script>

<template>
  <div class="jobs-view">
    <AsciiTable
      title="active jobs"
      :columns="columns"
      :rows="activeRows"
      :formatCell="formatCell"
      :minWidth="72"
      :collapsible="false"
      emptyText="(no active jobs)"
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
      emptyText="(no completed jobs)"
      :clickableRows="true"
      noType
      @rowClick="onJobRowClick"
    />
    <div v-if="hiddenCount" class="dim expand" @click="showAll = !showAll">
      {{ showAll ? '[ collapse ]' : `[ show all (${hiddenCount} more) ]` }}
    </div>

    <JobPopup :job="selectedJob" @close="selectedJob = null" />
  </div>
</template>

<style scoped>
.jobs-view { display: flex; flex-direction: column; }
.expand { font-size: var(--fs-sm); cursor: pointer; padding: var(--sp-xxs) var(--sp-sm); }
.expand:hover { color: var(--green); }
</style>
