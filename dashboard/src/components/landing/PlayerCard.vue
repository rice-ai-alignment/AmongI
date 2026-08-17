<script setup>
import { computed } from "vue";
import AmongUsBean from "./AmongUsBean.vue";

const props = defineProps({ player: Object, rank: Number });

const wins = computed(() => props.player.wins || 0);
const games = computed(() => props.player.games || 0);
const losses = computed(() => Math.max(0, games.value - wins.value));
const winRate = computed(() => (games.value > 0 ? Math.round((wins.value / games.value) * 100) : 0));
const isTop = computed(() => props.rank === 1 && games.value > 0);

const barBlocks = computed(() => {
  const filled = Math.round(winRate.value / 10);
  return "█".repeat(filled) + "░".repeat(Math.max(0, 10 - filled));
});
</script>

<template>
  <div class="pcard" :class="{ top: isTop }">
    <div class="phead">
      <span class="rank" :class="{ g: isTop }">#{{ rank }}</span>
      <span class="pname">{{ player.name || "?" }}</span>
    </div>
    <AmongUsBean :color="player.color || '#4fe87c'" size="96px" />
    <div class="prow">
      <span class="chip win">{{ wins }}W</span>
      <span class="chip loss">{{ losses }}L</span>
      <span class="chip rate">{{ winRate }}%</span>
    </div>
    <div class="bar g">{{ barBlocks }}</div>
    <div class="stat-line dim">🔪 {{ player.kills || 0 }} kills · imposter {{ player.times_imposter || 0 }}×</div>
  </div>
</template>

<style scoped>
.pcard {
  position: relative; display: flex; flex-direction: column; align-items: center;
  gap: var(--sp-xxs); padding: var(--sp-sm) var(--sp-xs);
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
}
.pcard.top { border-color: var(--amber); }
.phead { display: flex; gap: var(--sp-xxs); align-items: baseline; width: 100%; justify-content: center; }
.rank { font-size: var(--fs-sm); color: var(--text-dim); }
.pname {
  font-weight: 700; font-size: var(--fs-base); color: var(--text);
  text-align: center; max-width: 100%; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.prow { display: flex; gap: var(--sp-xxs); font-size: var(--fs-sm); align-items: center; }
.chip {
  padding: 1px var(--sp-xxs); border-radius: var(--radius-sm);
  font-weight: 700; background: var(--bg3, rgba(255, 255, 255, 0.06));
}
.chip.win  { color: var(--green); }
.chip.loss { color: var(--red); }
.chip.rate { color: var(--amber); }
.bar { font-size: var(--fs-sm); letter-spacing: 0; }
.stat-line { font-size: var(--fs-sm); }
</style>
