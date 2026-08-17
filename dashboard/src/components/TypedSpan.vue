<script setup>
import { ref, onMounted, onUnmounted, watch } from "vue";
import Typed from "typed.js";

import { TYPE } from "../composables/typeSettings.js";

const props = defineProps({
  text: String,
  speed: { type: Number, default: TYPE.normal },
  delay: { type: Number, default: 0 },
  cursor: { type: Boolean, default: false },
  contentType: { type: String, default: "html" },
  maxTyped: { type: Number, default: 0 },  // 0 = type everything
  clazz: { type: String, default: "" },
});

const el = ref(null);
let instance = null;
let typedOnce = false;

function start() {
  if (!el.value) return;
  if (instance) instance.destroy();
  const full = props.text || "";
  const cap = props.maxTyped;
  const visible = cap > 0 && full.length > cap ? full.slice(0, cap) : full;
  instance = new Typed(el.value, {
    strings: [visible],
    typeSpeed: props.speed,
    startDelay: 100 + props.delay,
    showCursor: true,
    cursorChar: "█",
    contentType: props.contentType,
    onComplete: (self) => {
      if (self.cursor) self.cursor.remove();
      typedOnce = true;
      // Append the remainder instantly if we capped the typed portion
      if (visible !== full) {
        el.value.appendChild(document.createTextNode(full.slice(cap)));
      }
    },
  });
}

onMounted(() => start());

// Live-updating text (timers, statuses) must NOT restart the typewriter
// every tick — after the initial animation, updates render instantly.
watch(() => props.text, (newText) => {
  if (!el.value) return;
  if (typedOnce || (instance && instance.isComplete)) {
    if (instance) { instance.destroy(); instance = null; }
    el.value.innerHTML = newText;
  } else {
    start();
  }
});

onUnmounted(() => { if (instance) instance.destroy(); });
</script>

<template>
  <span ref="el" :class="['typed-span', clazz]"></span>
</template>

<style scoped>
.typed-span { white-space: pre; }
</style>
