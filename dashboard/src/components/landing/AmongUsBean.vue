<script setup>
import { computed } from "vue";

const props = defineProps({
  color: { type: String, default: "#C51111" },
  size: { type: [Number, String], default: 80 },
});

function shade(hex, percent) {
  let h = (hex || "#4fe87c").replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const num = parseInt(h, 16) || 0;
  let r = (num >> 16) + Math.round(255 * percent);
  let g = ((num >> 8) & 0x00ff) + Math.round(255 * percent);
  let b = (num & 0x0000ff) + Math.round(255 * percent);
  r = Math.min(255, Math.max(0, r));
  g = Math.min(255, Math.max(0, g));
  b = Math.min(255, Math.max(0, b));
  return `#${(1 << 24 | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

const dark = computed(() => shade(props.color, -0.35));
const darker = computed(() => shade(props.color, -0.5));
const px = computed(() => (typeof props.size === "number" ? props.size + "px" : props.size));
</script>

<template>
  <svg :width="px" :height="px" viewBox="0 0 120 160" class="bean">
    <ellipse cx="60" cy="151" rx="44" ry="7" fill="black" opacity="0.28" />
    <rect x="2" y="58" width="26" height="58" rx="13" :fill="darker" />
    <rect x="26" y="128" width="18" height="28" rx="9" :fill="dark" />
    <rect x="66" y="128" width="18" height="28" rx="9" :fill="dark" />
    <path
      d="M22,138 Q10,138 10,116 L10,64 Q10,6 62,6 Q114,6 114,64 L114,108 Q114,140 92,140 Z"
      :fill="color" :stroke="darker" stroke-width="5" stroke-linejoin="round"
    />
    <ellipse cx="80" cy="52" rx="32" ry="21" fill="#bfe9ff" stroke="#5b8aa8" stroke-width="4" />
    <ellipse cx="90" cy="44" rx="9" ry="5" fill="#ffffff" opacity="0.7" />
  </svg>
</template>

<style scoped>
.bean { display: block; filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.45)); }
</style>
