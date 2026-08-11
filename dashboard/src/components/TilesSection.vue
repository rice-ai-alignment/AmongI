<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  stats: Object,
  config: Object,
});

const AGENT_COLORS = ["g", "r", "a", "", "c-d2", "c-d4"];

const total = computed(() => props.stats?.total_games || 0);
const byWinner = computed(() => props.stats?.by_winner || {});

const typeParts = computed(() => {
  const types = (props.config?.agents?.types || []).filter(t => t.id);
  return types.map((t, i) => {
    const wins = byWinner.value[t.id] || 0;
    const rate = total.value > 0 ? (wins / total.value) * 100 : 0;
    const cls = AGENT_COLORS[i % AGENT_COLORS.length];
    return `<span class="${cls}">${rate.toFixed(0)}% ${t.id}</span> (${wins})`;
  });
});

const line = computed(() => {
  if (!props.stats) return "(loading)";
  let s = ` <b>${String(total.value).padStart(2)}</b> games `;
  s += typeParts.value.join("  ");
  s += `  <b>${props.stats?.total_kills || 0}</b> kills  <b>${props.stats?.total_ejections || 0}</b> eject`;
  return s;
});
</script>

<template>
  <TerminalCard title="overview" :min-width="56">
    <TypedSpan :text="line" :speed="TYPE.fast + 5" :delay="200" />
  </TerminalCard>
</template>
