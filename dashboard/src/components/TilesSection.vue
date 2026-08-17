<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import { winningGroups, groupWins, paletteCls } from "../composables/experimentStats.js";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  stats: Object,
  config: Object,
});

const total = computed(() => props.stats?.total_games || 0);

const typeParts = computed(() => {
  const groups = winningGroups(props.config);
  return groupWins(props.stats, groups).map(g => {
    const cls = paletteCls(g.key);
    return `<span class="${cls}">${g.pct}% ${g.label}</span> (${g.wins})`;
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
