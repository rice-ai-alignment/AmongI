<script setup>
import { ref, computed } from "vue";
import ConfigTree from "./ConfigTree.vue";

const props = defineProps({
  config: { type: Object, default: null },
  title: { type: String, default: "config" },
});

const tab = ref("tree");

const prettyJson = computed(() => {
  if (!props.config) return "";
  return JSON.stringify(props.config, null, 2);
});
</script>

<template>
  <div class="config-card" v-if="config">
    <div class="tab-bar">
      <span class="tab" :class="{ active: tab === 'tree' }" @click="tab = 'tree'">[ tree ]</span>
      <span class="tab" :class="{ active: tab === 'json' }" @click="tab = 'json'">[ json ]</span>
    </div>

    <ConfigTree v-if="tab === 'tree'" :config="config" :title="title" />

    <div v-else class="json-view">
      <pre class="json-pre"><code>{{ prettyJson }}</code></pre>
    </div>
  </div>
  <ConfigTree v-else :config="null" :title="title" />
</template>

<style scoped>
.config-card {
  display: flex; flex-direction: column;
}

.tab-bar {
  display: flex; gap: var(--sp-xl);
  padding: var(--sp-xxs) 0 var(--sp-xs);
  margin-bottom: var(--sp-xs);
  border-bottom: var(--border-hair);
  flex-shrink: 0;
}
.tab {
  font-size: var(--fs-sm); color: var(--text-dim); cursor: pointer;
}
.tab:hover  { color: var(--text); }
.tab.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }

.json-view {
  overflow: hidden;
}
.json-pre {
  font-family: var(--font-mono);
  font-size: var(--fs-base);
  line-height: var(--lh-body);
  color: var(--text-dim);
  white-space: pre;
  overflow-x: auto;
  overflow-y: auto;
  max-height: 70vh;
  padding: var(--sp-sm) 0;
}
.json-pre::-webkit-scrollbar       { width: var(--scrollbar-w); height: var(--scrollbar-w); }
.json-pre::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }
</style>
