<script setup>
import { ref, computed, onMounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import ConfigTree from "./ConfigTree.vue";

const props = defineProps({
  config: { type: Object, default: null },
  title: { type: String, default: "config" },
  /** If true, show [ edit ] tab with save-to-experiment. */
  editable: { type: Boolean, default: false },
});

const emit = defineEmits(["saved"]);
const { user, activeStudyId, activeExperimentId, saveExperimentConfig, loadExperimentConfig } = useFirestore();

const tab = ref("tree");
const schema = ref(null);
const result = ref(null);
const editJson = ref("");
const editError = ref("");
const saving = ref(false);
const saved = ref(false);

const prettyJson = computed(() => {
  if (!props.config) return "";
  return JSON.stringify(props.config, null, 2);
});

onMounted(async () => {
  try {
    const res = await fetch("/schema.json");
    schema.value = await res.json();
  } catch (e) { /* schema not available */ }
});

function startEdit() {
  editJson.value = prettyJson.value;
  editError.value = "";
  saved.value = false;
  tab.value = "edit";
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
    // Notify parent so App.vue can refresh configJson
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

function validateNode(node, path, s, errors, warnings) {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) {
    node.forEach((item, i) => validateNode(item, `${path}[${i}]`, s, errors, warnings));
    return;
  }

  const t = node.type;
  const c = node.class;
  if (!t || !c) return; // leaf value, skip

  // Check type/class exist in schema
  const typeInfo = s[t];
  if (!typeInfo) {
    errors.push(`${path}: unknown type "${t}"`);
    return;
  }
  const classInfo = (typeInfo.classes || {})[c];
  if (!classInfo) {
    errors.push(`${path}: unknown class "${t}::${c}"`);
    return;
  }

  // Check param types
  const params = classInfo.params || {};
  for (const [key, val] of Object.entries(node)) {
    if (key === "type" || key === "class") continue;
    const p = params[key];
    if (p === undefined) continue; // extra keys are fine (could be nested config)

    const ptype = p.type;
    if (val === null || val === undefined) continue;

    // Type check
    const jsType = Array.isArray(val) ? "list" : typeof val;
    if (ptype === "int" || ptype === "float") {
      if (typeof val !== "number") {
        errors.push(`${path}.${key}: expected ${ptype}, got ${jsType}`);
      }
    } else if (ptype === "str") {
      if (typeof val !== "string") {
        errors.push(`${path}.${key}: expected str, got ${jsType}`);
      }
    } else if (ptype === "bool") {
      if (typeof val !== "boolean") {
        errors.push(`${path}.${key}: expected bool, got ${jsType}`);
      }
    } else if (ptype === "list") {
      if (!Array.isArray(val)) {
        errors.push(`${path}.${key}: expected list, got ${jsType}`);
      } else if (p.element_type && p.element_type !== "component") {
        for (let i = 0; i < val.length; i++) {
          const ev = val[i];
          if (p.element_type === "str" && typeof ev !== "string") {
            errors.push(`${path}.${key}[${i}]: expected str, got ${typeof ev}`);
          }
        }
      }
    }

    // Recurse into nested objects
    if (val && typeof val === "object") {
      validateNode(val, `${path}.${key}`, s, errors, warnings);
    }
  }
}

function validate() {
  if (!schema.value) {
    result.value = { valid: false, errors: ["Schema not loaded — cannot validate"], warnings: [] };
    return;
  }
  if (!props.config) {
    result.value = { valid: false, errors: ["No config to validate"], warnings: [] };
    return;
  }

  const errors = [];
  const warnings = [];

  // Legacy format check
  if (props.config.type === "Experiment") {
    warnings.push("Legacy 'Experiment' type — consider migrating to a Game type (e.g. AmongUsGame) with a 'phases' list.");
  }

  // Game type should have phases
  if (props.config.type === "Game" && (!props.config.phases || !props.config.phases.length)) {
    warnings.push("No 'phases' defined — the game has no gameplay phases.");
  }

  // Walk the tree
  validateNode(props.config, props.config.type || "root", schema.value, errors, warnings);

  result.value = {
    valid: errors.length === 0,
    errors,
    warnings,
    config_type: `${props.config.type || "?"} :: ${props.config.class || "?"}`,
  };
}
</script>

<template>
  <div class="config-card" v-if="config">
    <div class="tab-bar">
      <span class="tab" :class="{ active: tab === 'tree' }" @click="tab = 'tree'">[ tree ]</span>
      <span class="tab" :class="{ active: tab === 'json' }" @click="tab = 'json'">[ json ]</span>
      <span class="tab" :class="{ active: tab === 'edit' }" @click="startEdit" v-if="editable">[ edit ]</span>
      <span class="tab" :class="{ active: tab === 'validate' }" @click="tab = 'validate'; validate()">[ validate ]</span>
    </div>

    <ConfigTree v-if="tab === 'tree'" :config="config" :title="title" />

    <div v-else-if="tab === 'json'" class="json-view">
      <pre class="json-pre"><code>{{ prettyJson }}</code></pre>
    </div>

    <div v-else-if="tab === 'edit'" class="edit-view">
      <div class="edit-hint dim" v-if="!user">sign in to save config</div>
      <textarea
        v-model="editJson"
        class="edit-area"
        spellcheck="false"
        rows="24"
      ></textarea>
      <div class="edit-bar">
        <button class="run-btn" @click="saveConfig" :disabled="saving || !user">
          {{ saving ? 'saving...' : '[ save to experiment ]' }}
        </button>
        <span v-if="saved" class="g">✓ saved</span>
        <span v-if="editError" class="r">{{ editError }}</span>
      </div>
    </div>

    <div v-else class="validate-view">
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

.json-pre {
  font-family: var(--font-mono); font-size: var(--fs-base); line-height: var(--lh-body);
  color: var(--text-dim); white-space: pre; overflow: auto; max-height: 70vh;
  padding: var(--sp-sm) 0;
}
.json-pre::-webkit-scrollbar       { width: var(--scrollbar-w); height: var(--scrollbar-w); }
.json-pre::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }

/* Edit tab */
.edit-view { display: flex; flex-direction: column; flex: 1; }
.edit-area {
  flex: 1; min-height: 50vh;
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
  color: var(--text); font: var(--fs-base) var(--font-mono); line-height: var(--lh-body);
  padding: var(--sp-sm); outline: none; resize: vertical; tab-size: 2;
}
.edit-area:focus { border-color: var(--green); }
.edit-bar {
  display: flex; align-items: center; gap: var(--sp-sm);
  padding: var(--sp-xs) 0;
}
.run-btn {
  background: none; border: var(--border-accent); border-radius: var(--radius-sm);
  color: var(--green); font: var(--fs-md) var(--font-mono);
  padding: 1px var(--sp-sm); cursor: pointer;
  text-shadow: 0 0 5px rgba(79,232,124,0.3);
}
.run-btn:hover { background: rgba(79,232,124,0.1); }
.run-btn:disabled { opacity: 0.4; cursor: default; }
.edit-hint { font-size: var(--fs-sm); padding-bottom: var(--sp-xxs); }

.validate-view { font-family: var(--font-mono); font-size: var(--fs-base); padding-top: var(--sp-xs); }
.val-result { font-size: var(--fs-ui); margin-bottom: var(--sp-sm); }
.val-errors, .val-warnings { margin-top: var(--sp-xs); line-height: var(--lh-loose); }
</style>
