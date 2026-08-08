<script setup>
import { ref, computed, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";
import AsciiTable from "./AsciiTable.vue";

const { servers } = useFirestore();

const now = ref(Date.now());
const tick = setInterval(() => { now.value = Date.now(); }, 1000);
onUnmounted(() => clearInterval(tick));

const COLUMNS = [
  { key: "name", header: "NAME" },
  { key: "status", header: "STATUS" },
  { key: "cpu", header: "CPU%", align: "right" },
  { key: "mem", header: "MEM%", align: "right" },
  { key: "gpu", header: "GPU%", align: "right" },
  { key: "jobs", header: "JOBS", align: "right" },
  { key: "funnel", header: "FUNNEL" },
  { key: "seen", header: "SEEN" },
];

function formatCell(key, val, row) {
  if (key === "name") return { text: row.name || row.id || "?", bold: true };
  if (key === "status") return _statusCell(row);
  if (key === "cpu") return { text: row.cpu_percent != null ? String(Math.round(row.cpu_percent)) : "-" };
  if (key === "mem") return { text: row.memory_percent != null ? String(Math.round(row.memory_percent)) : "-" };
  if (key === "gpu") return { text: row.gpu_percent != null ? String(Math.round(row.gpu_percent)) : "-" };
  if (key === "jobs") return { text: String(row.jobs_completed || 0) };
  if (key === "funnel") return { text: row.funnel_url ? "yes" : "-" };
  if (key === "seen") return { text: _ageText(row) };
  return { text: String(val ?? "-") };
}

function _statusCell(row) {
  const offline = _isOffline(row);
  if (offline) return { text: "offline", cls: "r" };
  if (row.status === "busy") return { text: "busy", cls: "a" };
  return { text: "online", cls: "g" };
}

function _isOffline(row) {
  if (!row.last_seen) return true;
  const interval = (row.heartbeat_interval_sec || 30) * 1000;
  const last = row.last_seen.toDate ? row.last_seen.toDate().getTime() : Date.parse(row.last_seen);
  if (isNaN(last)) return false;
  return (now.value - last) > (interval * 2 + 15000);
}

function _ageText(row) {
  if (!row.last_seen) return "never";
  const last = row.last_seen.toDate ? row.last_seen.toDate().getTime() : Date.parse(row.last_seen);
  if (isNaN(last)) return "?";
  const sec = Math.round((now.value - last) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  return `${Math.round(sec / 3600)}h ago`;
}
</script>

<template>
  <TerminalCard title="servers" :min-width="88">
    <AsciiTable
      v-if="servers.length"
      :columns="COLUMNS"
      :rows="servers"
      :formatCell="formatCell"
      :row-delay="40"
    />
    <div v-else class="dim">(no servers connected)</div>
  </TerminalCard>
</template>
