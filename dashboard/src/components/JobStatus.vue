<script setup>
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";
import AsciiTable from "./AsciiTable.vue";

const { jobs } = useFirestore();

const COLUMNS = [
  { key: "status", header: "STATUS" },
  { key: "created", header: "CREATED" },
  { key: "server", header: "SERVER" },
  { key: "games", header: "GAMES" },
  { key: "done", header: "DONE" },
];

function formatCell(key, val, row) {
  if (key === "status") return _statusCell(row);
  if (key === "created") {
    const d = row.created_at;
    if (!d) return { text: "-" };
    const t = d.toDate ? d.toDate() : new Date(d);
    return { text: t.toLocaleString("sv").replace("T", " ").slice(0, 16) };
  }
  if (key === "server") return { text: row.claimed_by || "-" };
  if (key === "games") {
    const g = row.result?.games ?? 0;
    return { text: String(g) };
  }
  if (key === "done") {
    if (!row.finished_at) return { text: "-" };
    const t = row.finished_at.toDate ? row.finished_at.toDate() : new Date(row.finished_at);
    return { text: t.toLocaleString("sv").replace("T", " ").slice(0, 16) };
  }
  return { text: String(val ?? "-") };
}

function _statusCell(row) {
  const s = row.status;
  if (s === "queued") return { text: "queued", cls: "a" };
  if (s === "claimed" || s === "running") return { text: s, cls: "g" };
  if (s === "completed") return { text: "completed", cls: "" };
  if (s === "failed" || s === "cancelled") return { text: s, cls: "r" };
  return { text: s || "-" };
}
</script>

<template>
  <TerminalCard title="jobs" :min-width="88">
    <AsciiTable
      v-if="jobs.length"
      :columns="COLUMNS"
      :rows="jobs"
      :formatCell="formatCell"
      :row-delay="40"
    />
    <div v-else class="dim">(no jobs yet)</div>
  </TerminalCard>
</template>
