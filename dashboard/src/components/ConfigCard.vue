<script setup>
import { ref, computed, onMounted, nextTick } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import ConfigTree from "./ConfigTree.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  config: { type: Object, default: null },
  title: { type: String, default: "config" },
  editable: { type: Boolean, default: false },
});

const emit = defineEmits(["saved", "update"]);
const { user, activeStudyId, activeExperimentId, saveExperimentConfig } = useFirestore();

const tab = ref("tree");
const schema = ref(null);
const result = ref(null);
const editJson = ref("");
const editError = ref("");
const saving = ref(false);
const saved = ref(false);

// ── Inline tree editing ───────────────────────────────────────────
const inlineEdit = ref({ active: false, x: 0, y: 0, path: [], value: "" });

function onTreeClick(e) {
  if (!props.editable) return;
  const el = e.target.closest("[data-leaf]");
  if (!el) { inlineEdit.value.active = false; return; }
  const path = JSON.parse(el.dataset.path);
  const current = String(el.dataset.value || "");
  const rect = el.getBoundingClientRect();
  inlineEdit.value = {
    active: true,
    x: rect.left, y: rect.top,
    path, value: current,
  };
  nextTick(() => {
    const inp = document.querySelector(".inline-tree-input");
    if (inp) inp.focus();
  });
}

function commitInlineEdit() {
  if (!inlineEdit.value.active) return;
  const { path, value } = inlineEdit.value;
  let obj = props.config;
  for (let i = 0; i < path.length - 1; i++) obj = obj[path[i]];
  const key = path[path.length - 1];
  const old = obj[key];
  // Parse back to original type
  if (typeof old === "number") obj[key] = parseFloat(value) || 0;
  else if (typeof old === "boolean") obj[key] = value === "true";
  else obj[key] = value;
  inlineEdit.value.active = false;
  emit("update", { ...props.config });
}

function cancelInlineEdit() {
  inlineEdit.value.active = false;
}

const prettyJson = computed(() => {
  if (!props.config) return "";
  return JSON.stringify(props.config, null, 2);
});

onMounted(async () => {
  try {
    const res = await fetch("/schema.json");
    schema.value = await res.json();
    // Load the shared compiler (same JS used by the Python/Node pipeline)
    if (!window.validateConfig) {
      await new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "/schema_compiler.js";
        s.onload = resolve;
        s.onerror = () => reject(new Error("compiler script failed to load"));
        document.head.appendChild(s);
      });
    }
  } catch (e) { /* schema not available */ }
});

function openJsonTab() {
  editJson.value = prettyJson.value;
  editError.value = "";
  saved.value = false;
  tab.value = "json";
}

async function saveConfig() {
  if (!activeStudyId.value || !activeExperimentId.value) {
    editError.value = "No active experiment selected.";
    return;
  }
  saving.value = true;
  editError.value = "";
  saved.value = false;
  try {
    const parsed = JSON.parse(editJson.value);
    await saveExperimentConfig(activeStudyId.value, activeExperimentId.value, parsed);
    saved.value = true;
    emit("saved", parsed);
  } catch (e) {
    if (e instanceof SyntaxError) {
      editError.value = "Invalid JSON: " + e.message;
    } else {
      editError.value = "Save failed: " + (e.message || e);
      console.error("[ConfigCard] Save error:", e);
    }
  } finally {
    saving.value = false;
  }
}

function validate() {
  if (!schema.value) {
    result.value = { valid: false, errors: ["Schema not loaded"], warnings: [] };
    return;
  }
  if (!props.config) {
    result.value = { valid: false, errors: ["No config to validate"], warnings: [] };
    return;
  }
  // Use the shared compiler — same code as the Python/Node pipeline
  if (window.validateConfig) {
    const { errors, warnings } = window.validateConfig(props.config, schema.value);
    result.value = {
      valid: errors.length === 0, errors, warnings,
      config_type: `${props.config.type || "?"} :: ${props.config.class || "?"}`,
    };
  } else {
    result.value = {
      valid: false,
      errors: ["Compiler not loaded — is /schema_compiler.js available?"],
      warnings: [],
    };
  }
}
</script>

<template>
  <div class="config-card" v-if="config">
    <div class="tab-bar">
      <span class="tab" :class="{ active: tab === 'tree' }" @click="tab = 'tree'">[ tree ]</span>
      <span class="tab" :class="{ active: tab === 'json' }" @click="openJsonTab">[ json ]</span>
      <span class="tab" :class="{ active: tab === 'validate' }" @click="tab = 'validate'; validate()">[ validate ]</span>
    </div>

    <div v-if="tab === 'tree'" @click="onTreeClick" class="tree-container">
      <ConfigTree :config="config" :title="title" :editable="editable && !!user" />
      <!-- Inline value editor -->
      <input
        v-if="inlineEdit.active"
        class="inline-tree-input"
        :style="{ left: inlineEdit.x + 'px', top: inlineEdit.y + 'px' }"
        v-model="inlineEdit.value"
        @keyup.enter="commitInlineEdit"
        @keyup.escape="cancelInlineEdit"
        @blur="commitInlineEdit"
      />
    </div>

    <TerminalCard v-else-if="tab === 'json'" title="json" :min-width="48" :collapsible="false">
      <div v-if="!user && editable" class="dim">sign in to edit</div>
      <textarea
        v-model="editJson"
        class="edit-area"
        :class="{ readonly: !editable || !user }"
        :readonly="!editable || !user"
        spellcheck="false"
        rows="24"
      ></textarea>
      <div v-if="editable && user" class="edit-bar">
        <button class="run-btn" @click="saveConfig" :disabled="saving">
          {{ saving ? 'saving...' : '[ save ]' }}
        </button>
        <span v-if="saved" class="g">✓ saved</span>
        <span v-if="editError" class="r">{{ editError }}</span>
      </div>
    </TerminalCard>

    <TerminalCard v-else title="validate" :min-width="48" :collapsible="false">
      <div class="validate-view">
        <div v-if="!schema" class="dim">loading schema...</div>
        <div v-else-if="result">
          <div class="val-result" :class="result.valid ? 'g' : 'r'">
            {{ result.valid ? '✓ valid' : '✗ invalid' }}
            <span class="dim"> — {{ result.config_type }}</span>
          </div>
          <div v-if="result.errors.length" class="val-errors">
            <div v-for="(e, i) in result.errors" :key="'e'+i" class="r">  ✗ {{ e }}</div>
          </div>
          <div v-if="result.warnings && result.warnings.length" class="val-warnings">
            <div v-for="(w, i) in result.warnings" :key="'w'+i" class="a">  ⚠ {{ w }}</div>
          </div>
        </div>
      </div>
    </TerminalCard>
  </div>
  <ConfigTree v-else :config="null" :title="title" />
</template>

<style scoped>
.config-card { display: flex; flex-direction: column; }
.tab-bar {
  display: flex; gap: var(--sp-xl);
  padding: var(--sp-xxs) 0 var(--sp-xs);
  margin-bottom: var(--sp-xs);
  border-bottom: var(--border-hair); flex-shrink: 0;
}
.tab { font-size: var(--fs-sm); color: var(--text-dim); cursor: pointer; }
.tab:hover  { color: var(--text); }
.tab.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }

.edit-area {
  width: 100%; min-height: 40vh;
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
  color: var(--text); font: var(--fs-base) var(--font-mono); line-height: var(--lh-body);
  padding: var(--sp-sm); outline: none; resize: vertical; tab-size: 2;
}
.edit-area:focus { border-color: var(--green); }
.edit-area.readonly { color: var(--text-dim); cursor: default; }

.edit-bar {
  display: flex; align-items: center; gap: var(--sp-sm);
  padding-top: var(--sp-xs);
}
.run-btn {
  background: none; border: var(--border-accent); border-radius: var(--radius-sm);
  color: var(--green); font: var(--fs-md) var(--font-mono);
  padding: 1px var(--sp-sm); cursor: pointer;
  text-shadow: 0 0 5px rgba(79,232,124,0.3);
}
.run-btn:hover { background: rgba(79,232,124,0.1); }
.run-btn:disabled { opacity: 0.4; cursor: default; }

.tree-container { position: relative; }
.inline-tree-input {
  position: fixed; z-index: 150;
  background: var(--bg-deep); border: 1px solid var(--green);
  color: var(--text); font: var(--fs-base) var(--font-mono);
  padding: 0 var(--sp-xxs); outline: none;
  min-width: 6ch; box-shadow: 0 0 8px rgba(79,232,124,0.2);
}

.validate-view { font-family: var(--font-mono); font-size: var(--fs-base); }
.val-result { font-size: var(--fs-ui); margin-bottom: var(--sp-sm); }
.val-errors, .val-warnings { margin-top: var(--sp-xs); line-height: var(--lh-loose); }
</style>
