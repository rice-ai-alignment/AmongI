<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({ stats: Object });
const total = computed(() => props.stats?.total_games || 0);
const byWinner = computed(() => props.stats?.by_winner || {});
const crewWins = computed(() => byWinner.value.crewmates || 0);
const impWins = computed(() => byWinner.value.imposters || 0);
const crewRate = computed(() => total.value > 0 ? (crewWins.value / total.value) * 100 : 0);
const impRate = computed(() => total.value > 0 ? (impWins.value / total.value) * 100 : 0);

const line = computed(() => {
  if (!props.stats) return "(loading)";
  return ` <b>${String(total.value).padStart(2)}</b> games  <span class="g">${String(crewRate.value.toFixed(0)).padStart(3)}%</span> crew (${crewWins.value})  <span class="r">${String(impRate.value.toFixed(0)).padStart(3)}%</span> imp (${impWins.value})  <b>${props.stats?.total_kills || 0}</b> kills  <b>${props.stats?.total_ejections || 0}</b> eject`;
});
</script>

<template>
  <TerminalCard title="overview" :min-width="56">
    <TypedSpan :text="line" :speed="TYPE.fast + 5" :delay="200" />
  </TerminalCard>
</template>
