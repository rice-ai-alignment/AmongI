<script setup>
import { ref, computed } from "vue";
import TypedSpan from "./TypedSpan.vue";

const props = defineProps({
  title: { type: String, default: "" },
  headSpeed: { type: Number, default: 10 },
  bodyDelay: { type: Number, default: 0 },
  minWidth: { type: Number, default: 36 },
  collapsible: { type: Boolean, default: true },
});

const collapsed = ref(false);

const box = computed(() => {
  const w = Math.max(props.minWidth, 40);
  const t = props.collapsible && collapsed.value
    ? "┌" + ("─ " + props.title + " [+] ").padEnd(w - 2, "─") + "┐"
    : "┌" + ("─ " + props.title + " ").padEnd(w - 2, "─") + "┐";
  const b = "└" + "─".repeat(w - 2) + "┘";
  return { top: t, btm: b };
});
</script>

<template>
  <div class="card-box">
    <div class="box-line box-top" @click="collapsed = !collapsed" :class="{ clickable: collapsible }">
      <TypedSpan :text="box.top" :speed="headSpeed" />
    </div>
    <div class="box-body" v-if="!collapsed">
      <slot />
    </div>
    <div class="box-line box-bot">{{ box.btm }}</div>
  </div>
</template>

<style scoped>
.card-box {
  background: var(--surface-1); margin-bottom: 4px; overflow: hidden;
  box-shadow: 0 0 6px rgba(79,232,124,0.04);
  animation: box-expand 0.3s ease backwards;
}
@keyframes box-expand { from { opacity: 0; transform: scaleY(0.8); } to { opacity: 1; transform: scaleY(1); } }
.box-line { font-size: 18px; white-space: pre; line-height: 1.2; padding: 2px 8px; overflow: hidden; }
.box-line.clickable { cursor: pointer; }
.box-top { color: var(--border-solid); text-shadow: 0 0 6px rgba(79,232,124,0.4); }
.box-bot { color: var(--border-solid); text-shadow: 0 0 4px rgba(79,232,124,0.3); }
.box-body { color: var(--text-dim); padding: 0 6px 0 calc(6px + 1ch); line-height: 1.6; overflow: hidden; white-space: pre; }
.box-body :deep(.g) { color: var(--green); }
.box-body :deep(.r) { color: var(--red); }
.box-body :deep(.a) { color: var(--amber); }
</style>
