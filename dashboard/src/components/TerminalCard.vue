<script setup>
import { ref, computed } from "vue";
import TypedSpan from "./TypedSpan.vue";

const props = defineProps({
  title: { type: String, default: "" },
  headSpeed: { type: Number, default: 10 },
  bodyDelay: { type: Number, default: 0 },
  minWidth: { type: Number, default: 30 },
  collapsible: { type: Boolean, default: true },
  startCollapsed: { type: Boolean, default: false },
});

const collapsed = ref(props.startCollapsed);

const label = computed(() =>
  props.collapsible && collapsed.value
    ? "─ " + props.title + " [+] "
    : "─ " + props.title + " "
);
</script>

<template>
  <div class="card-box" :style="{ width: (props.minWidth + 4) + 'ch' }">
    <!-- Top border: cap + typed title + flex-fill dashes + cap -->
    <div
      class="box-line box-top"
      :class="{ clickable: collapsible }"
      @click="collapsed = !collapsed"
    >
      <span class="cap">┌</span><!--
   --><TypedSpan :text="label" :speed="headSpeed" /><!--
   --><span class="fill" aria-hidden="true"></span><!--
   --><span class="cap">┐</span>
    </div>

    <div class="box-body" v-if="!collapsed">
      <slot />
    </div>

    <!-- Bottom border: cap + flex-fill dashes + cap -->
    <div class="box-line box-bot">
      <span class="cap">└</span><!--
   --><span class="fill" aria-hidden="true"></span><!--
   --><span class="cap">┘</span>
    </div>
  </div>
</template>

<style scoped>
/* ── Box container ──────────────────────────────────────────── */
.card-box {
  font-size: var(--fs-base);   /* ch unit matches body content, not border */
  max-width: 100%;
  background: var(--surface-1); margin-bottom: var(--sp-xs);
  overflow-x: hidden; overflow-y: auto;
  box-shadow: 0 0 6px rgba(79,232,124,0.06), inset 0 0 4px rgba(79,232,124,0.03);
  animation: box-expand 0.3s ease backwards;
}

@keyframes box-expand {
  0%   { clip-path: inset(0 100% 100% 0); opacity: 0; }
  5%   { opacity: 1; }
  40%  { clip-path: inset(0 0 100% 0); }
  100% { clip-path: inset(0 0 0 0); }
}
.card-box:nth-child(1) { animation-delay: 0.05s; }
.card-box:nth-child(2) { animation-delay: 0.12s; }
.card-box:nth-child(3) { animation-delay: 0.19s; }
.card-box:nth-child(4) { animation-delay: 0.26s; }

/* ── Border bars ────────────────────────────────────────────── */
.box-line {
  display: flex; align-items: baseline;
  font-size: var(--fs-ui); line-height: var(--lh-tight);
  padding: 0 var(--sp-sm); overflow: hidden;
  white-space: nowrap;
}
.box-line.clickable { cursor: pointer; }
.box-top { color: var(--green); text-shadow: var(--glow-medium); }
.box-bot { color: var(--green); text-shadow: var(--glow-soft); }

.cap { flex-shrink: 0; white-space: pre; }

/* Flex-fill: consumes remaining space, ::after dashes clipped by overflow */
.fill {
  flex: 1 1 0; min-width: 0;
  overflow: hidden; white-space: nowrap;
}
.fill::after {
  content: "────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────";
  white-space: nowrap;
}

/* ── Body ───────────────────────────────────────────────────── */
.box-body {
  color: var(--text-dim); font-size: var(--fs-base);
  padding: var(--sp-xxs) 1ch;
  line-height: var(--lh-loose);
  white-space: pre;
}
.box-body :deep(b)       { color: var(--text); }
.box-body :deep(.g)      { color: var(--green); }
.box-body :deep(.r)      { color: var(--red); }
.box-body :deep(.a)      { color: var(--amber); }
.box-body :deep(.dim)    { color: var(--text-dim); }
.box-body :deep(.spacer) { flex: 1; }
</style>
