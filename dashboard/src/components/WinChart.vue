<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import { winningGroups, otherOutcomes, paletteCls } from "../composables/experimentStats.js";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  stats: Object,
  config: Object,
});

const bars = computed(() => {
  if (!props.stats) return [];
  const bw = props.stats?.by_winner || {};
  const total = props.stats?.total_games || 0;
  const maxBar = 22;

  // Winning groups from the experiment config + leftover system outcomes
  const groups = winningGroups(props.config);
  const others = otherOutcomes(props.stats, groups);

  const result = [];

  for (const g of groups) {
    const count = bw[g.key] || 0;
    const n = total > 0 ? Math.max(0, Math.round((count / total) * maxBar)) : 0;
    const bar = "█".repeat(n);
    const pad = " ".repeat(maxBar - n);
    const cls = paletteCls(g.key);
    result.push({
      delay: result.length * 200,
      line: ` <span class="${cls}">${g.label.padEnd(12)}</span> <span class="${cls}">${bar}</span>${pad} <b>${String(count).padStart(2)}</b>`
    });
  }

  for (const o of others) {
    const n = total > 0 ? Math.max(0, Math.round((o.wins / total) * maxBar)) : 0;
    const bar = "█".repeat(n);
    const pad = " ".repeat(maxBar - n);
    result.push({
      delay: result.length * 200,
      line: ` <span class="dim">${o.label.padEnd(12)}</span> <span class="dim">${bar}</span>${pad} <b>${String(o.wins).padStart(2)}</b>`
    });
  }

  return result;
});
</script>

<template>
  <TerminalCard title="win distribution" :min-width="56" v-if="bars.length">
    <div v-for="b in bars" :key="b.delay">
      <TypedSpan :text="b.line" :speed="TYPE.fast + 5" :delay="200 + b.delay" />
    </div>
  </TerminalCard>
</template>
