<script setup>
import { computed } from "vue";
import AsciiTable from "./AsciiTable.vue";

const props = defineProps({ games: Array });

const columns = [
  { key: "ts",       header: "ended",       align: "left" },
  { key: "game_id",  header: "game",        align: "left" },
  { key: "winner",   header: "winner",      align: "left" },
  { key: "kills",    header: "k",           align: "right" },
  { key: "ejections",header: "e",           align: "right" },
  { key: "duration", header: "duration",    align: "left" },
];

function fmtDur(sec) {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  return `${m}m${Math.round(sec % 60)}s`;
}

function formatCell(key, value, row) {
  if (key === "winner") {
    const cls = value === "crewmates" ? "g" : value === "imposters" ? "r" : "a";
    return { text: value, cls };
  }
  return { text: value };
}

const rows = computed(() => {
  const recent = [...(props.games || [])].reverse().slice(0, 20);
  return recent.map(g => ({
    ts:        g.ended_at ? new Date(g.ended_at).toISOString().slice(0, 16).replace("T", " ") : "?",
    game_id:   g.game_id || "?",
    winner:    g.winner || "?",
    kills:     String(g.kills || 0),
    ejections: String(g.ejections || 0),
    duration:  fmtDur(g.duration_sec),
  }));
});
</script>

<template>
  <AsciiTable
    title="match log"
    :columns="columns"
    :rows="rows"
    :formatCell="formatCell"
    :minWidth="66"
  />
</template>
