<script setup>
import { computed } from "vue";
import AsciiTable from "./AsciiTable.vue";

const props = defineProps({ stats: Object });

const columns = [
  { key: "name",  header: "player", align: "left" },
  { key: "games", header: "gms",    align: "right" },
  { key: "wins",  header: "wins",   align: "right" },
  { key: "rate",  header: "rate",   align: "right" },
  { key: "imp",   header: "imp",    align: "right" },
  { key: "kills", header: "kills",  align: "right" },
];

function formatCell(key, value, row) {
  if (key === "name") {
    return { text: value || "?", style: `color:${row.color || "#4fe87c"}`, bold: true };
  }
  if (key === "wins" || key === "rate") {
    const cls = row._wins > 0 ? "g" : "n";
    return { text: value, cls };
  }
  if (key === "imp" || key === "kills") {
    const has = key === "imp" ? row._imp > 0 : row._kills > 0;
    return { text: value, cls: has ? "r" : "n" };
  }
  return { text: value };
}

const rows = computed(() => {
  const players = props.stats?.players || [];
  return players.map(p => {
    const wr = p.games > 0 ? (p.wins / p.games * 100).toFixed(0) + "%" : "0%";
    return {
      name:  p.name || "?",
      games: String(p.games || 0),
      wins:  String(p.wins || 0),
      rate:  wr,
      imp:   String(p.times_imposter || 0),
      kills: String(p.kills || 0),
      color: p.color,
      // raw flags for formatCell
      _wins:  p.wins || 0,
      _imp:   p.times_imposter || 0,
      _kills: p.kills || 0,
    };
  });
});
</script>

<template>
  <AsciiTable
    title="players"
    :columns="columns"
    :rows="rows"
    :formatCell="formatCell"
    :minWidth="50"
  />
</template>
