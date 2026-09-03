<script setup>
import { ref, computed, watch, onMounted, reactive } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import { useTypewriter } from "../composables/useTypewriter.js";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";
import ConfirmPopup from "./ConfirmPopup.vue";
import FormPopup from "./FormPopup.vue";
import StaggerBlock from "./StaggerBlock.vue";

const {
  user, studies, activeStudyId, loadStudies, createStudy, archiveStudy,
  experiments, activeExperimentId, studyExperiments, createExperiment, archiveExperiment,
  loadAllExperiments, loadExperiments, fetchData, setDescription, saveExperimentConfig,
  duplicateStudy, duplicateExperiment,
} = useFirestore();

const emit = defineEmits(["browsing"]);
const mode = ref("studies");
const input = ref("");
const descInput = ref("");
const editingDesc = ref("");
const creating = ref(false);
const confirmArchive = ref(null); // { type: 'study'|'experiment', id, name }
const confirmDuplicate = ref(null); // { type: 'study'|'experiment', id, name }
const duplicating = ref(false);
const studiesLabel = ref(null);
const sideLabel = ref(null);

// ── Popup state ──────────────────────────────────────────────────────
const createStudyPopup = ref(false);
const createExperimentPopup = ref(false);
const studyFields = [
  { key: "name", label: "name", placeholder: "my-study" },
  { key: "description", label: "desc", placeholder: "optional description", required: false },
];
// ── Example configs for template dropdown ─────────────────────────────
const exampleConfigs = ref([]);  // [{name, filename, json}]

onMounted(async () => {
  const files = [
    { name: "basic (crew + imposter, 5 games)", file: "/sample_data/among_us/example_basic.json" },
    { name: "small kill (fast kills)", file: "/sample_data/among_us/example_small_kill.json" },
    { name: "timer (short rounds)", file: "/sample_data/among_us/example_timer.json" },
  ];
  const loaded = [];
  for (const f of files) {
    try {
      const res = await fetch(f.file);
      if (res.ok) {
        const json = await res.json();
        loaded.push({ name: f.name, filename: f.file.split("/").pop(), json });
      }
    } catch (e) { /* skip unavailable files */ }
  }
  exampleConfigs.value = loaded;
});

const experimentTemplate = ref("blank");
const templateOptions = computed(() => {
  const opts = [{ value: "blank", label: "(blank — configure later)" }];
  for (const ex of exampleConfigs.value) {
    opts.push({ value: ex.filename, label: ex.name });
  }
  return opts;
});

const experimentFields = computed(() => [
  { key: "name", label: "name", placeholder: "baseline-run" },
  { key: "description", label: "desc", placeholder: "optional description", required: false },
  { key: "template", label: "template", type: "select",
    options: templateOptions.value, default: "blank" },
]);

useTypewriter(studiesLabel, "┌─ studies ─┐", { typeSpeed: TYPE.normal, startDelay: 100 });

const activeStudy = computed(() => studies.value.find(s => s.id === activeStudyId.value));

useTypewriter(sideLabel, () => `┌─ ${activeStudy.value?.name || "?"} ─┐`, { typeSpeed: TYPE.normal, startDelay: 150 });

function match(q, items) {
  if (!q) return items;
  const lq = q.toLowerCase();
  return items.filter(i => i.id.includes(lq) || i.name.toLowerCase().includes(lq));
}

async function runCmd(raw) {
  const cmd = raw.trim();
  if (!cmd) return;
  const args = cmd.split(/\s+/);
  const c = args[0]; const a = args.slice(1).join(" ");

  if ((c === "cd" || c === "open") && a) {
    if (mode.value === "studies") {
      const s = studies.value.find(s => s.id === a || s.name.toLowerCase() === a.toLowerCase());
      if (s) { activeStudyId.value = s.id; mode.value = "experiments"; emit("browsing", true); await loadAllExperiments(); }
    } else {
      const e = experiments.value.find(e => e.id === a || e.name.toLowerCase() === a.toLowerCase());
      if (e) { activeExperimentId.value = e.id; mode.value = "viewing"; emit("browsing", false); await loadAllExperiments(); }
    }
  } else if (c === "cd" && a === "..") {
    activeStudyId.value = null; activeExperimentId.value = null;
    mode.value = "studies"; emit("browsing", true);
  }
  input.value = "";
}

// ── Popup handlers ───────────────────────────────────────────────────

async function onConfirmStudy(form) {
  createStudyPopup.value = false;
  const name = form.name.trim();
  if (!name) return;
  creating.value = true;
  const id = await createStudy(name);
  creating.value = false;
  if (id) {
    // Set description if provided
    if (form.description.trim()) {
      await setDescription("study", id, null, form.description.trim());
      await loadStudies();
    }
    activeStudyId.value = id;
    mode.value = "experiments";
    emit("browsing", true);
    await loadAllExperiments();
  }
}

async function onConfirmExperiment(form) {
  createExperimentPopup.value = false;
  const name = form.name.trim();
  if (!name) return;
  creating.value = true;
  const id = await createExperiment(name);
  creating.value = false;
  if (id) {
    if (form.description.trim()) {
      await setDescription("experiment", activeStudyId.value, id, form.description.trim());
      await loadExperiments();
    }
    // Save template config if one was selected
    if (form.template && form.template !== "blank") {
      const tpl = exampleConfigs.value.find(e => e.filename === form.template);
      if (tpl && tpl.json) {
        try {
          await saveExperimentConfig(activeStudyId.value, id, tpl.json);
        } catch (e) { console.warn("Failed to save template config:", e); }
      }
    }
    activeExperimentId.value = id;
    mode.value = "viewing";
    emit("browsing", false);
    await loadAllExperiments();
  }
}

async function selectStudy(id) {
  activeStudyId.value = id;
  mode.value = "experiments";
  emit("browsing", true);
  await loadExperiments();
}
async function selectExperiment(id) {
  activeExperimentId.value = id;
  mode.value = "viewing";
  emit("browsing", false);
}
function backToStudies() {
  activeStudyId.value = null; activeExperimentId.value = null;
  mode.value = "studies"; emit("browsing", true);
}

// Sync mode when study/experiment set externally (e.g. URL restore)
watch(activeExperimentId, (id) => {
  if (id && mode.value !== "viewing") {
    mode.value = "viewing";
    emit("browsing", false);
  }
});
watch(activeStudyId, (id) => {
  if (id && mode.value === "studies") {
    mode.value = "experiments";
    emit("browsing", true);
  }
});
</script>

<template>
  <!-- ASCII card grid: studies -->
  <div class="browser" v-if="mode === 'studies'" :key="'studies-' + studies.length">
    <div class="box-label" ref="studiesLabel">┌─ studies ─┐</div>
    <div class="card-grid">
      <div v-for="s in studies" :key="s.id" class="ascii-card" @click="selectStudy(s.id)">
        <div class="card-top">┌────────────────────────────────────────────────┐</div>
        <div class="card-row">│ <TypedSpan class="card-name" :text="s.name" :speed="TYPE.slow" /></div>
        <div class="card-row dim desc" @click.stop>
          │ <span v-if="editingDesc !== s.id" @click="editingDesc = s.id; descInput = s.description || ''">{{ s.description || '+ description' }}</span>
          <input v-else v-model="descInput" @keyup.enter="setDescription('study', s.id, null, descInput); editingDesc = ''; loadStudies()" @blur="setDescription('study', s.id, null, descInput); editingDesc = ''; loadStudies()" @keyup.escape="editingDesc = ''" class="card-inp" autofocus />
        </div>
        <div class="card-row dim exp-in-card" v-for="e in (studyExperiments[s.id] || []).slice(0, 3)" :key="e.id" @click.stop="activeStudyId = s.id; selectExperiment(e.id)">│   ▸ <TypedSpan :text="e.name" :speed="TYPE.slow" /></div>
        <div class="card-row dim" v-if="!(studyExperiments[s.id]||[]).length">│   empty</div>
        <div class="card-bot">└────────────────────────────────────────────────┘</div>
        <div class="card-actions" v-if="user" @click.stop>
          <span class="act-btn" @click="confirmDuplicate = { type: 'study', id: s.id, name: s.name }">[ duplicate ]</span>
          <span class="act-btn r-hov" @click="confirmArchive = { type: 'study', id: s.id, name: s.name }">[ archive ]</span>
        </div>
      </div>
      <div class="ascii-card card-new" v-if="user" @click="createStudyPopup = true">
        <div class="card-top">┌─ new ─────────────────────────────────────────┐</div>
        <div class="card-row dim">│   [ + new study ]</div>
        <div class="card-bot">└────────────────────────────────────────────────┘</div>
      </div>
    </div>
    <div class="cmd-line hint" v-if="!studies.length && !user">sign in to create the first study</div>
  </div>

  <!-- Sidebar when browsing experiments -->
  <div class="side-panel" v-else :key="activeStudyId">
    <div class="box-label" ref="sideLabel"></div>
    <StaggerBlock class="side-list">
      <div
        v-for="e in experiments"
        :key="e.id"
        class="exp-item"
        :class="{ active: e.id === activeExperimentId }"
        @click="selectExperiment(e.id)"
      >
        <span class="exp-name"><TypedSpan :text="e.name" :speed="TYPE.slow" /></span>
        <span v-if="user" class="exp-acts" @click.stop>
          <span class="act-btn" @click="confirmDuplicate = { type: 'experiment', id: e.id, name: e.name }">[ duplicate ]</span>
          <span class="act-btn r-hov" @click="confirmArchive = { type: 'experiment', id: e.id, name: e.name }">[ archive ]</span>
        </span>
      </div>
      <div class="exp-item dim" v-if="!experiments.length">  (empty)</div>
    </StaggerBlock>
    <div class="cmd-line" style="margin-top:var(--sp-xs)" v-if="user">
      <span v-if="creating">creating...</span>
      <span v-else class="new-link" @click="createExperimentPopup = true">$ [ + new experiment ]</span>
    </div>
    <div class="cmd-line dim back-link" @click="backToStudies">$ cd ..</div>
  </div>

  <!-- Archive confirmation popup -->
  <ConfirmPopup
    v-if="confirmArchive"
    :message="'archive ' + confirmArchive.name + '?'"
    :buttons="[
      { text: '[ cancel ]', action: 'cancel' },
      { text: '[ archive ]', action: 'confirm', danger: true },
    ]"
    @action="(act) => {
      if (act === 'confirm') {
        confirmArchive.type === 'study'
          ? archiveStudy(confirmArchive.id)
          : archiveExperiment(confirmArchive.id);
      }
      confirmArchive = null;
    }"
  />

  <!-- Duplicate popup — choose mode -->
  <ConfirmPopup
    v-if="confirmDuplicate"
    :message="'duplicate ' + confirmDuplicate.name + '?'"
    :buttons="[
      { text: '[ cancel ]', action: 'cancel' },
      { text: '[ settings only ]', action: 'settings' },
      { text: '[ all data + logs ]', action: 'alldata' },
    ]"
    @action="async (act) => {
      if (act === 'cancel') { confirmDuplicate = null; return; }
      duplicating = true;
      try {
        const include = act === 'alldata';
        if (confirmDuplicate.type === 'study') {
          await duplicateStudy(confirmDuplicate.id, include);
          await loadAllExperiments();
        } else {
          await duplicateExperiment(activeStudyId, confirmDuplicate.id, include);
          await loadExperiments();
        }
        loadStudies();
      } catch (e) {
        console.error('duplicate failed:', e.message);
      } finally {
        duplicating = false;
        confirmDuplicate = null;
      }
    }"
  />

  <!-- Create study popup -->
  <FormPopup
    v-if="createStudyPopup"
    title="new study"
    :fields="studyFields"
    confirmText="[ create ]"
    @confirm="onConfirmStudy"
    @cancel="createStudyPopup = false"
  />

  <!-- Create experiment popup -->
  <FormPopup
    v-if="createExperimentPopup"
    title="new experiment"
    :fields="experimentFields"
    confirmText="[ create ]"
    @confirm="onConfirmExperiment"
    @cancel="createExperimentPopup = false"
  />
</template>

<style scoped>
/* ── Cards ────────────────────────────────────────────────────── */
.browser { flex: 1; }
.box-label {
  font-size: var(--fs-ui); color: var(--green);
  text-shadow: var(--glow-medium); margin-bottom: var(--sp-sm);
  animation: glow-in 0.5s ease;
}
@keyframes blink-flash { 0% { opacity: 0; } 2% { opacity: 1; background: rgba(79,232,124,0.08); } 4% { opacity: 0; background: transparent; } 100% { opacity: 0; } }
.side-list :deep(*) { position: relative; }
.side-list :deep(*)::before { content: ""; position: absolute; inset: 0; pointer-events: none; animation: blink-flash 0.3s ease backwards; }
.card-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.ascii-card {
  cursor: pointer; color: var(--text-dim); line-height: var(--lh-card); white-space: nowrap;
  font-size: var(--fs-ui); transition: all 0.2s ease;
  animation: card-slide 0.35s ease backwards;
}
.card-grid > *:nth-child(1) { animation-delay: 0.05s; }
.card-grid > *:nth-child(2) { animation-delay: 0.10s; }
.card-grid > *:nth-child(3) { animation-delay: 0.15s; }
.card-grid > *:nth-child(4) { animation-delay: 0.20s; }
.card-grid > *:nth-child(5) { animation-delay: 0.25s; }
.card-grid > *:nth-child(6) { animation-delay: 0.30s; }
@keyframes card-slide { from { opacity: 0; transform: translateX(-12px); } to { opacity: 1; transform: translateX(0); } }
.ascii-card:hover { transform: translateY(-1px); }
.ascii-card:hover .card-name { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }
.ascii-card:active { transform: translateY(0); }
.card-top, .card-bot { color: var(--green); text-shadow: var(--glow-soft); }
.card-row { color: var(--text-dim); }
.card-name { color: var(--text); }
.exp-in-card { cursor: pointer; }
.exp-in-card:hover { color: var(--green); }
.card-new { opacity: 0.4; transition: all 0.3s ease; }
.card-new:hover { opacity: 0.8; }
.card-inp {
  background: transparent; border: none; border-bottom: 1px solid rgba(79,232,124,0.2);
  color: var(--text); font: var(--fs-ui) var(--font-mono); outline: none; flex: 1; min-width: 0;
}
.card-inp:focus { border-bottom-color: var(--green); }
.dim { color: var(--text-dim); }
.hint { margin-top: var(--sp-md); }

/* ── Side panel ────────────────────────────────────────────────── */
.side-panel {
  width: 34ch; flex-shrink: 0;
  border-right: 2px solid var(--green); padding-right: 1ch;
}
.side-list { margin: var(--sp-xs) 0; }
.exp-item {
  font-size: var(--fs-ui); padding: var(--sp-xxs) 0; cursor: pointer;
  color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: all 0.15s ease;
  display: flex; align-items: baseline; gap: var(--sp-xxs);
}
.exp-item:hover { color: var(--text); padding-left: var(--sp-xxs); }
.exp-item.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }
.exp-name { flex-shrink: 0; }
.side-inp {
  background: transparent; border: none; border-bottom: var(--border-subtle);
  color: var(--text); font: var(--fs-ui) var(--font-mono); outline: none; width: 24ch;
}
.side-inp::placeholder { color: var(--text-dim); }
.cmd-line { font-size: var(--fs-ui); padding: 1px 0; }
.back-link { cursor: pointer; margin-top: var(--sp-sm); }
.back-link:hover { color: var(--green); }
.new-link { cursor: pointer; color: var(--text-dim); }
.new-link:hover { color: var(--green); }
.archive-btn {
  color: var(--text-dim); font-size: var(--fs-xs); cursor: pointer;
  flex-shrink: 0;
}
.archive-btn:hover { color: var(--red); }
.dup-btn {
  color: var(--text-dim); font-size: var(--fs-xs); cursor: pointer;
  flex-shrink: 0;
}
.dup-btn:hover { color: var(--green); }

/* Action buttons (always visible, below study card / beside experiment) */
.card-actions {
  display: flex; gap: var(--sp-sm);
  padding: var(--sp-xxs) var(--sp-xs) var(--sp-xs);
}
.exp-acts {
  display: inline-flex; gap: var(--sp-xs);
  margin-left: auto; flex-shrink: 0;
}
.act-btn {
  font-size: var(--fs-sm); color: var(--text-dim);
  cursor: pointer; white-space: nowrap;
}
.act-btn:hover { color: var(--green); }
.act-btn.r-hov:hover { color: var(--red); }
.desc { max-width: 320px; overflow: hidden; text-overflow: ellipsis; }
.creating { color: var(--amber); animation: pulse 1s ease-in-out infinite; }
</style>
