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
  background: var(--surface-1); margin-bottom: var(--sp-xs);
  overflow-x: auto; overflow-y: hidden;
  box-shadow: var(--glow-subtle);
}
.card-box::-webkit-scrollbar { height: var(--scrollbar-w); }
.card-box::-webkit-scrollbar-thumb { background: var(--border); border-radius: var(--radius-sm); }
.box-line.clickable { cursor: pointer; }
.box-body {
  color: var(--text-dim);
  padding: 0 var(--sp-sm) 0 calc(var(--sp-sm) + 1ch);
  line-height: var(--lh-loose); overflow: hidden;
}
.box-body :deep(.g) { color: var(--green); }
.box-body :deep(.r) { color: var(--red); }
.box-body :deep(.a) { color: var(--amber); }
</style>
