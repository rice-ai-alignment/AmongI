<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";

const props = defineProps({ stats: Object });
const bars = computed(() => {
  if (!props.stats) return null;
  const bw = props.stats?.by_winner || {};
  const total = props.stats?.total_games || 0;
  const maxBar = 22;
  const meta = [
    { key: "crewmates", label: "crewmates " },
    { key: "imposters", label: "imposters " },
    { key: "timeout", label: "timeout   " },
    { key: "token_limit", label: "token lim " },
  ];
  const lines = meta.map((m, i) => {
    const count = bw[m.key] || 0;
    const n = total > 0 ? Math.max(0, Math.round((count / total) * maxBar)) : 0;
    const bar = "█".repeat(n);
    const pad = " ".repeat(maxBar - n);
    const c = m.key === "crewmates" ? "g" : m.key === "imposters" ? "r" : "a";
    return { delay: i * 200,
      line: ` <span class="${c}">${m.label}</span> <span class="${c}">${bar}</span>${pad} <b>${String(count).padStart(2)}</b>` };
  });
  const w = Math.max(...lines.map(l => l.line.replace(/<[^>]+>/g,"").length + 4), 36);
  const title = "─ win distribution ";
  return {
    top: "┌" + title + "─".repeat(w - 2 - title.length) + "┐",
    btm: "└" + "─".repeat(w - 2) + "┘",
    lines,
  };
});
</script>

<template>
  <div class="card-box" v-if="bars">
    <div class="box-line box-top"><TypedSpan :text="bars.top" :speed="TYPE.fast" /></div>
    <div class="box-body">
      <div v-for="b in bars.lines" :key="b.delay">
        <TypedSpan :text="b.line" :speed="TYPE.fast + 5" :delay="200 + b.delay" />
      </div>
    </div>
    <div class="box-line box-bot">{{ bars.btm }}</div>
  </div>
</template>
