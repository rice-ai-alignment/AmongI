<script setup>
import { ref } from "vue";

const props = defineProps({
  command: { type: String, default: "" },
  label: { type: String, default: "copy command" },
});

const copied = ref(false);

async function doCopy() {
  if (!props.command) return;
  try {
    await navigator.clipboard.writeText(props.command);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 1500);
  } catch (e) {
    console.warn("Copy failed:", e);
  }
}
</script>

<template>
  <button class="cpy-btn" @click="doCopy" :title="command">
    {{ copied ? "copied ✓" : label }}
  </button>
</template>

<style scoped>
.cpy-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 2px;
  color: var(--text-dim);
  font: 15px var(--font-mono);
  padding: 1px 5px;
  cursor: pointer;
}
.cpy-btn:hover { color: var(--text); border-color: var(--text-dim); }
</style>
