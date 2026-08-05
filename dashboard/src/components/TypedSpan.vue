<script setup>
import { ref, onMounted, onUnmounted, watch } from "vue";
import Typed from "typed.js";

import { TYPE } from "../composables/typeSettings.js";

const props = defineProps({
  text: String,
  speed: { type: Number, default: TYPE.normal },
  delay: { type: Number, default: 0 },
  cursor: { type: Boolean, default: false },
});

const el = ref(null);
let instance = null;

function start() {
  if (!el.value) return;
  if (instance) instance.destroy();
  instance = new Typed(el.value, {
    strings: [props.text],
    typeSpeed: props.speed,
    startDelay: 100 + props.delay,
    showCursor: true,
    cursorChar: "█",
    contentType: "html",
    onComplete: (self) => {
      if (self.cursor) self.cursor.remove();
    },
  });
}

onMounted(() => start());
watch(() => props.text, () => start());
onUnmounted(() => { if (instance) instance.destroy(); });
</script>

<template>
  <span ref="el"></span>
</template>
