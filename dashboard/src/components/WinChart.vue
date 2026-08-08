<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({ stats: Object });
const bars = computed(() => {
  if (!props.stats) return [];
  const bw = props.stats?.by_winner || {};
  const total = props.stats?.total_games || 0;
  const meta = [
    { key: "crewmates", label: "crewmates ", cls: "g" },
    { key: "imposters", label: "imposters ", cls: "r" },
    { key: "timeout", label: "timeout   ", cls: "a" },
    { key: "token_limit", label: "token lim ", cls: "a" },
  ];
  const maxBar = 22;
  return meta.map((m, i) => {
    const count = bw[m.key] || 0;
    const n = total > 0 ? Math.max(0, Math.round((count / total) * maxBar)) : 0;
    const bar = "█".repeat(n);
    const pad = " ".repeat(maxBar - n);
    return { delay: i * 200,
      line: ` <span class="${m.cls}">${m.label}</span> <span class="${m.cls}">${bar}</span>${pad} <b>${String(count).padStart(2)}</b>` };
  });
});
</script>

<template>
  <TerminalCard title="win distribution" :min-width="56" v-if="bars.length">
    <div v-for="b in bars" :key="b.delay">
      <TypedSpan :text="b.line" :speed="TYPE.fast + 5" :delay="200 + b.delay" />
    </div>
  </TerminalCard>
</template>
