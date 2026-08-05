<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";

const props = defineProps({ stats: Object });
const total = computed(() => props.stats?.total_games || 0);
const byWinner = computed(() => props.stats?.by_winner || {});
const crewWins = computed(() => byWinner.value.crewmates || 0);
const impWins = computed(() => byWinner.value.imposters || 0);
const crewRate = computed(() => total.value > 0 ? (crewWins.value / total.value) * 100 : 0);
const impRate = computed(() => total.value > 0 ? (impWins.value / total.value) * 100 : 0);

const box = computed(() => {
  if (!props.stats) return null;
  const plain = ` games ${total.value}  crew ${crewRate.value.toFixed(0)}% (${crewWins.value})  imp ${impRate.value.toFixed(0)}% (${impWins.value})  kills ${props.stats?.total_kills || 0}  eject ${props.stats?.total_ejections || 0}`;
  const line = ` games <b>${total.value}</b>  crew <span class="g">${crewRate.value.toFixed(0)}%</span> (${crewWins.value})  imp <span class="r">${impRate.value.toFixed(0)}%</span> (${impWins.value})  kills <b>${props.stats?.total_kills || 0}</b>  eject <b>${props.stats?.total_ejections || 0}</b>`;
  const w = Math.max(plain.length + 4, 36);
  const title = "─ overview ";
  return {
    top: "┌" + title + "─".repeat(w - 2 - title.length) + "┐",
    btm: "└" + "─".repeat(w - 2) + "┘",
    line,
  };
});
</script>

<template>
  <div class="card-box" v-if="box">
    <div class="box-line box-top"><TypedSpan :text="box.top" :speed="TYPE.fast" /></div>
    <div class="box-body"><TypedSpan :text="box.line" :speed="TYPE.fast + 5" :delay="200" /></div>
    <div class="box-line box-bot">{{ box.btm }}</div>
  </div>
</template>
