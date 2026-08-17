<script setup>
import TypedSpan from "../TypedSpan.vue";
import { TYPE } from "../../composables/typeSettings.js";

const props = defineProps({
  label: String,
  value: [String, Number],
  icon: { type: String, default: "" },
  accent: { type: String, default: "var(--green)" },
});
</script>

<template>
  <div class="tile" :style="{ '--accent': accent }">
    <div class="tile-label dim">{{ icon }} {{ label }}</div>
    <div class="tile-value">
      <TypedSpan :text="String(value)" :speed="TYPE.fast" />
    </div>
  </div>
</template>

<style scoped>
.tile {
  background: var(--bg-deep);
  border: var(--border-subtle);
  border-top: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  padding: var(--sp-xxs) var(--sp-md) var(--sp-xs);
  min-width: 150px;
  text-align: left;
}
.tile-label {
  font-size: var(--fs-sm); text-transform: uppercase; letter-spacing: 0.08em;
}
.tile-value {
  font-size: 26px; font-weight: 700; line-height: 1.15; color: var(--accent);
  text-shadow: 0 0 8px color-mix(in srgb, var(--accent) 40%, transparent);
}
</style>
