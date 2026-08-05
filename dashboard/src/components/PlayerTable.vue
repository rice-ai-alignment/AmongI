<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";

const props = defineProps({ stats: Object });
const players = computed(() => props.stats?.players || []);

const box = computed(() => {
  if (!props.stats) return null;
  const lines = players.value.length
    ? players.value.map((p, i) => {
        const wr = p.games > 0 ? (p.wins / p.games * 100).toFixed(0) + "%" : "0%";
        const wc = p.wins > 0 ? "g" : "";
        const ic = p.times_imposter > 0 ? "r" : "";
        const kc = p.kills > 0 ? "r" : "";
        return { delay: i * 100, line:
          ` <b>${(p.name||"?").padEnd(12)}</b> ${String(p.games).padStart(3)}g  <span class="${wc}">${String(p.wins).padStart(3)}w</span>  <span class="${wc}">${wr.padStart(4)}</span>  imp:<span class="${ic}">${String(p.times_imposter).padStart(2)}</span>  kills:<span class="${kc}">${String(p.kills).padStart(2)}</span>` };
      })
    : [{ delay: 0, line: "  (no players)" }];
  const w = Math.max(...lines.map(l => l.line.replace(/<[^>]+>/g,"").length + 4), 36);
  const title = "─ players ";
  return {
    top: "┌" + title + "─".repeat(w - 2 - title.length) + "┐",
    btm: "└" + "─".repeat(w - 2) + "┘",
    lines,
  };
});
</script>

<template>
  <div class="card-box" v-if="box">
    <div class="box-line box-top"><TypedSpan :text="box.top" :speed="TYPE.fast" /></div>
    <div class="box-body">
      <div v-for="l in box.lines" :key="l.delay">
        <TypedSpan :text="l.line" :speed="TYPE.fast" :delay="200 + l.delay" />
      </div>
    </div>
    <div class="box-line box-bot">{{ box.btm }}</div>
  </div>
</template>
