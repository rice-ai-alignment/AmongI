<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  stats: Object,
  config: Object,
});

// Stable color per type ID — deterministic, won't shift on re-render
const TYPE_COLORS = ["g", "r", "c-d3", "c-d4", "c-d5", "c-d6", "c-d2", "a"];

function colorForType(typeId, idx) {
  // Use a simple hash of the type id string for stability
  let h = 0;
  for (let i = 0; i < typeId.length; i++) h = (h * 31 + typeId.charCodeAt(i)) | 0;
  return TYPE_COLORS[Math.abs(h) % TYPE_COLORS.length];
}

const bars = computed(() => {
  if (!props.stats) return [];
  const bw = props.stats?.by_winner || {};
  const total = props.stats?.total_games || 0;
  const maxBar = 22;

  // Agent types from config (known groups)
  const agentTypes = (props.config?.agents?.types || [])
    .filter(t => t.id)
    .map(t => t.id);

  // System keys that aren't agent types
  const systemKeys = Object.keys(bw).filter(k =>
    !agentTypes.includes(k) && bw[k] > 0
  );

  const result = [];

  // Agent type bars
  for (const key of agentTypes) {
    const count = bw[key] || 0;
    const n = total > 0 ? Math.max(0, Math.round((count / total) * maxBar)) : 0;
    const bar = "█".repeat(n);
    const pad = " ".repeat(maxBar - n);
    const cls = colorForType(key);
    result.push({
      delay: result.length * 200,
      line: ` <span class="${cls}">${key.padEnd(12)}</span> <span class="${cls}">${bar}</span>${pad} <b>${String(count).padStart(2)}</b>`
    });
  }

  // System keys (timeout, token_limit, old legacy keys)
  for (const key of systemKeys) {
    const count = bw[key] || 0;
    const n = total > 0 ? Math.max(0, Math.round((count / total) * maxBar)) : 0;
    const bar = "█".repeat(n);
    const pad = " ".repeat(maxBar - n);
    result.push({
      delay: result.length * 200,
      line: ` <span class="dim">${key.padEnd(12)}</span> <span class="dim">${bar}</span>${pad} <b>${String(count).padStart(2)}</b>`
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
