<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";

const props = defineProps({
  text: { type: String, default: "" },
  speed: { type: Number, default: 2 },   // ms per character
  cursor: { type: Boolean, default: true },
  clazz: { type: String, default: "" },
});

// Each line reserves its space via an invisible "ghost" (so the popup
// scroll height is right from the start) and a typed span overlays it.
// Lines type out one at a time as they scroll into view.
const rootEl = ref(null);
const lines = computed(() => (props.text || "").split("\n"));
const typedCounts = ref([]);
const typing = ref([]);

let observer = null;
const timers = [];
const started = [];

function startLine(i) {
  if (started[i]) return;
  started[i] = true;
  const full = lines.value[i].length;
  const step = full > 400 ? 2 : 1;   // long lines chunk so they finish fast
  let n = 0;
  typing.value[i] = true;
  const iv = setInterval(() => {
    n += step;
    typedCounts.value[i] = Math.min(n, full);
    if (n >= full) {
      clearInterval(iv);
      timers[i] = null;
      typing.value[i] = false;
    }
  }, props.speed);
  timers[i] = iv;
}

function setupObserver() {
  if (observer) observer.disconnect();
  if (!rootEl.value) return;
  const rows = rootEl.value.querySelectorAll("[data-tline]");
  if (!rows.length) return;
  observer = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (en.isIntersecting) {
        startLine(parseInt(en.target.dataset.tline, 10));
        observer.unobserve(en.target);
      }
    }
  }, { threshold: 0.05 });
  rows.forEach((r) => observer.observe(r));
}

onMounted(() => {
  typedCounts.value = lines.value.map(() => 0);
  typing.value = lines.value.map(() => false);
  setupObserver();
});

onUnmounted(() => {
  if (observer) observer.disconnect();
  for (const iv of timers) if (iv) clearInterval(iv);
});
</script>

<template>
  <div ref="rootEl" :class="['typed-lines', clazz]">
    <div v-for="(line, i) in lines" :key="i" class="tline" :data-tline="i">
      <!-- Ghost reserves exact space so the scroll height never jumps -->
      <span class="tline-ghost">{{ line || " " }}</span>
      <span class="tline-typed">{{ line.slice(0, typedCounts[i]) }}<span v-if="cursor && typing[i]" class="tcur">█</span></span>
    </div>
  </div>
</template>

<style scoped>
.typed-lines { position: relative; }
.tline { position: relative; }
.tline-ghost,
.tline-typed {
  white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;
}
.tline-ghost { visibility: hidden; }
.tline-typed { position: absolute; left: 0; top: 0; width: 100%; }
.tcur { color: var(--green); }
</style>
