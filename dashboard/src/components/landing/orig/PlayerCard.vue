<script setup>
import { computed } from "vue";
import AmongUsBean from "./AmongUsBean.vue";

const props = defineProps({ player: Object, rank: Number });

const wins = computed(() => props.player.wins || 0);
const games = computed(() => props.player.games || 0);
const losses = computed(() => Math.max(0, games.value - wins.value));
const winRate = computed(() => (games.value > 0 ? Math.round((wins.value / games.value) * 100) : 0));
const isTop = computed(() => props.rank === 1 && games.value > 0);
</script>

<template>
  <div class="pcard" :class="{ top: isTop }">
    <div class="crown" v-if="isTop">👑</div>
    <AmongUsBean :color="player.color || '#4fe87c'" size="6.4vw" />
    <div class="pname">{{ player.name || "?" }}</div>
    <div class="prow">
      <span class="chip win">{{ wins }}W</span>
      <span class="chip loss">{{ losses }}L</span>
      <span class="chip rate">{{ winRate }}%</span>
    </div>
    <div class="bar">
      <div class="bar-fill" :style="{ width: winRate + '%' }"></div>
    </div>
    <div class="stat-line">🔪 <b>{{ player.kills || 0 }}</b> kills</div>
    <div class="stat-line">🕵️ imposter <b>{{ player.times_imposter || 0 }}</b>×</div>
  </div>
</template>

<style scoped>
.pcard {
  position: relative;
  display: flex; flex-direction: column; align-items: center;
  gap: 0.35vw;
  padding: 1.1vw 0.8vw 0.9vw;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.14);
}
.pcard.top {
  border-color: #ffd85e;
  box-shadow: 0 0 20px rgba(255, 216, 94, 0.35);
  background: rgba(255, 216, 94, 0.06);
}
.crown {
  position: absolute; top: -1.1vw; font-size: 1.7vw;
  filter: drop-shadow(0 0 6px rgba(255, 216, 94, 0.7));
}
.pname {
  font-weight: 700; font-size: 1.25vw; color: #f2f5ff;
  text-align: center; max-width: 11vw; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.prow { display: flex; gap: 0.5vw; font-size: 0.9vw; align-items: center; }
.chip {
  padding: 0.12vw 0.55vw; border-radius: 3px; font-weight: 700;
  background: rgba(255, 255, 255, 0.08);
}
.chip.win  { color: #6dffb0; background: rgba(109, 255, 176, 0.14); }
.chip.loss { color: #ff8f8f; background: rgba(255, 143, 143, 0.14); }
.chip.rate { color: #ffd85e; background: rgba(255, 216, 94, 0.14); }

.bar {
  width: 90%; height: 5px; border-radius: 3px; margin-top: 0.2vw;
  background: rgba(255, 255, 255, 0.08); overflow: hidden;
}
.bar-fill { height: 100%; background: linear-gradient(90deg, #4fe87c, #6dffb0); }

.stat-line { font-size: 0.88vw; color: #b7c1d6; }
.stat-line b { color: #eef2ff; }
</style>
