<script setup>
import { computed } from "vue";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";

const props = defineProps({ games: Array });
const recent = computed(() => [...(props.games || [])].reverse().slice(0, 20));
function fmt(sec) { if (sec==null) return ""; const m=Math.floor(sec/60); return `${m}m${Math.round(sec%60)}s`; }

const box = computed(() => {
  const lines = recent.value.length
    ? recent.value.map((g, i) => {
        const ts = g.ended_at ? new Date(g.ended_at).toISOString().slice(0,16).replace('T',' ') : "?";
        const w = g.winner || "?";
        const wc = w === "crewmates" ? "g" : w === "imposters" ? "r" : "a";
        return { delay: i * 80, line:
          ` ${ts}  ${g.game_id||"?"}  <span class="${wc}">${w}</span>  k:<b>${g.kills||0}</b>  e:<b>${g.ejections||0}</b>  ${fmt(g.duration_sec)}` };
      })
    : [{ delay: 0, line: "  (no matches)" }];
  const w = Math.max(...lines.map(l => l.line.replace(/<[^>]+>/g,"").length + 4), 36);
  const title = "─ match log ";
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
