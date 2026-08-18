<script setup>
import { computed } from "vue";

const props = defineProps({
  label: String,
  value: [String, Number],
  icon: { type: String, default: "" },
  accent: { type: String, default: "#4fe87c" },
});

const glow = computed(() => props.accent + "66");
</script>

<template>
  <div class="tile" :style="{ '--accent': accent, '--glow': glow }">
    <div class="tile-icon" v-if="icon">{{ icon }}</div>
    <div class="tile-value">{{ value }}</div>
    <div class="tile-label">{{ label }}</div>
  </div>
</template>

<style scoped>
.tile {
  background: rgba(255, 255, 255, 0.05);
  border: 2px solid var(--accent);
  border-radius: 18px;
  padding: 1vw 1.6vw;
  text-align: center;
  min-width: 130px;
  box-shadow: 0 0 22px var(--glow);
  backdrop-filter: blur(2px);
}
.tile-icon { font-size: 2vw; line-height: 1; margin-bottom: 0.25vw; }
.tile-value {
  font-size: 2.8vw; font-weight: 800; color: var(--accent); line-height: 1;
  text-shadow: 0 0 18px var(--glow);
}
.tile-label {
  margin-top: 0.4vw; font-size: 0.9vw; letter-spacing: 0.09em;
  text-transform: uppercase; color: #cfd8e3; opacity: 0.85;
}
</style>
