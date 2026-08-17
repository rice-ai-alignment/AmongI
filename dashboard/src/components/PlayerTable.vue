<script setup>
import { computed } from "vue";
import AsciiTable from "./AsciiTable.vue";
import { sortedPlayers } from "../composables/experimentStats.js";

const props = defineProps({ stats: Object, config: Object });

const columns = [
  { key: "name",  header: "AGENT",  align: "left" },
  { key: "role",  header: "ROLE",   align: "left" },
  { key: "games", header: "TRIALS",  align: "right" },
  { key: "wins",  header: "WINS",   align: "right" },
  { key: "rate",  header: "RATE",   align: "right" },
  { key: "kills", header: "KILLS",  align: "right" },
];

function formatCell(key, val, row) {
  if (key === "name") return { text: val, bold: true, style: `color:${row._color || "var(--text)"}` };
  if (key === "role") return { text: val, cls: "dim" };
  if (key === "wins" || key === "rate") return { text: val, cls: row._wins > 0 ? "g" : "dim" };
  if (key === "kills") return { text: val, cls: row._kills > 0 ? "r" : "dim" };
  return { text: val };
}

const allRows = computed(() => {
  const players = sortedPlayers(props.stats);
  return players.map(p => {
    const wr = p.games > 0 ? (p.wins / p.games * 100).toFixed(0) + "%" : "0%";
    return {
      name:  p.name || "?",
      role:  p.role || p.agent_type || "-",
      games: String(p.games || 0),
      wins:  String(p.wins || 0),
      rate:  wr,
      kills: String(p.kills || 0),
      _color: p.color || "",
      _wins: p.wins || 0,
      _kills: p.kills || 0,
    };
  });
});

const agentTypes = computed(() =>
  (props.config?.agents?.types || []).map(t => t.id)
);

const grouped = computed(() => {
  const rows = allRows.value;
  const types = agentTypes.value;
  const groups = {};
  for (const tid of types) groups[tid] = [];
  groups["_other"] = [];

  for (const r of rows) {
    const match = types.find(t => t && r.role && t.toLowerCase() === r.role.toLowerCase());
    const key = match || "_other";
    groups[key].push(r);
  }
  return groups;
});
</script>

<template>
  <div v-if="allRows.length">
    <div v-for="tid in agentTypes" :key="tid">
      <AsciiTable
        v-if="grouped[tid] && grouped[tid].length"
        :title="tid + ' stats'"
        :columns="columns"
        :rows="grouped[tid]"
        :formatCell="formatCell"
        :minWidth="56"
        :collapsible="true"
      />
    </div>
    <AsciiTable
      v-if="grouped._other && grouped._other.length"
      title="agents"
      :columns="columns"
      :rows="grouped._other"
      :formatCell="formatCell"
      :minWidth="56"
      :collapsible="true"
    />
  </div>
  <AsciiTable
    v-else
    title="agent stats"
    :columns="columns"
    :rows="[]"
    emptyText="(no data yet)"
    :minWidth="50"
  />
</template>
