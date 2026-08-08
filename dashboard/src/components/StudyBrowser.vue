<script setup>
import { ref, computed, watch } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import { useTypewriter } from "../composables/useTypewriter.js";
import { TYPE } from "../composables/typeSettings.js";
import TypedSpan from "./TypedSpan.vue";
import ConfirmPopup from "./ConfirmPopup.vue";
import StaggerBlock from "./StaggerBlock.vue";

const {
  user, studies, activeStudyId, loadStudies, createStudy, archiveStudy,
  experiments, activeExperimentId, studyExperiments, createExperiment, archiveExperiment,
  loadAllExperiments, loadExperiments, fetchData, setDescription,
} = useFirestore();

const emit = defineEmits(["browsing"]);
const mode = ref("studies");
const input = ref("");
const descInput = ref("");
const editingDesc = ref("");
const creating = ref(false);
const confirmArchive = ref(null); // { type: 'study'|'experiment', id, name }
const studiesLabel = ref(null);
const sideLabel = ref(null);

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
  } else if ((c === "create" || c === "new") && user.value) {
    const rest = args.slice(1).join(" ");
    if ((args[1] === "study" || args[1] === "s") && rest !== "study") {
      const name = args.slice(2).join(" ");
      if (name) { creating.value = true; const id = await createStudy(name); creating.value = false; if (id) { activeStudyId.value = id; mode.value = "experiments"; emit("browsing", true); await loadAllExperiments(); } }
    } else if ((args[1] === "experiment" || args[1] === "exp" || args[1] === "e") && activeStudyId.value && rest !== "experiment") {
      const name = args.slice(2).join(" ");
      if (name) { creating.value = true; const id = await createExperiment(name); creating.value = false; if (id) { activeExperimentId.value = id; mode.value = "viewing"; emit("browsing", false); await loadAllExperiments(); } }
    }
  }
  input.value = "";
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
        <div class="card-top">┌──────────────────────────────────┐</div>
        <div class="card-row">│ <TypedSpan class="card-name" :text="s.name" :speed="TYPE.slow" /> <span v-if="user" class="archive-btn" @click.stop="confirmArchive = { type: 'study', id: s.id, name: s.name }" title="archive">[x]</span></div>
        <div class="card-row dim desc" @click.stop>
          │ <span v-if="editingDesc !== s.id" @click="editingDesc = s.id; descInput = s.description || ''">{{ s.description || '+ description' }}</span>
          <input v-else v-model="descInput" @keyup.enter="setDescription('study', s.id, null, descInput); editingDesc = ''; loadStudies()" @blur="setDescription('study', s.id, null, descInput); editingDesc = ''; loadStudies()" @keyup.escape="editingDesc = ''" class="card-inp" autofocus />
        </div>
        <div class="card-row dim exp-in-card" v-for="e in (studyExperiments[s.id] || []).slice(0, 3)" :key="e.id" @click.stop="activeStudyId = s.id; selectExperiment(e.id)">│   ▸ <TypedSpan :text="e.name" :speed="TYPE.slow" /></div>
        <div class="card-row dim" v-if="!(studyExperiments[s.id]||[]).length">│   empty</div>
        <div class="card-bot">└──────────────────────────────────┘</div>
      </div>
      <div class="ascii-card card-new" v-if="user">
        <div class="card-top">┌─ new ───────────────────────────┐</div>
        <div class="card-row">│ $ <input v-model="input" @keyup.enter="runCmd('create study '+input)" placeholder="create study <name>" class="card-inp" /></div>
        <div class="card-bot">└──────────────────────────────────┘</div>
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
      > <TypedSpan :text="e.name" :speed="TYPE.slow" /> <span v-if="user" class="archive-btn" @click.stop="confirmArchive = { type: 'experiment', id: e.id, name: e.name }" title="archive">[x]</span></div>
      <div class="exp-item dim" v-if="!experiments.length">  (empty)</div>
    </StaggerBlock>
    <div class="cmd-line" style="margin-top:4px" v-if="user">
      <span v-if="creating">creating...</span>
      <span v-else>$ <input v-model="input" @keyup.enter="runCmd('create experiment '+input)" :placeholder="'create experiment name'" class="side-inp" /></span>
    </div>
    <div class="cmd-line dim back-link" @click="backToStudies">$ cd ..</div>
  </div>

  <!-- Archive confirmation popup (reusable component) -->
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
</template>

<style scoped>
/* ── Cards ────────────────────────────────────────────────────── */
.browser { flex: 1; }
.box-label { font-size: 18px; color: var(--green); text-shadow: 0 0 6px rgba(79,232,124,0.4); margin-bottom: 6px; animation: glow-in 0.5s ease; }
@keyframes glow-in { from { text-shadow: 0 0 0 transparent; } to { text-shadow: 0 0 6px rgba(79,232,124,0.4); } }
@keyframes type-in { from { opacity: 0; transform: translateY(2px); } to { opacity: 1; transform: translateY(0); } }
@keyframes blink-flash { 0% { opacity: 0; } 2% { opacity: 1; background: rgba(79,232,124,0.08); } 4% { opacity: 0; background: transparent; } 100% { opacity: 0; } }
/* staggered type-in rules are now in StaggerBlock.vue */
.side-list :deep(*) { position: relative; }
.side-list :deep(*)::before { content: ""; position: absolute; inset: 0; pointer-events: none; animation: blink-flash 0.3s ease backwards; }
.card-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.ascii-card {
  cursor: pointer; color: var(--text-dim); line-height: 1.55; white-space: nowrap; font-size: 18px;
  transition: all 0.2s ease;
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
.card-top, .card-bot { color: var(--border-solid); text-shadow: 0 0 4px rgba(79,232,124,0.3); }
.card-row { color: var(--text-dim); }
.card-name { color: var(--text); }
.exp-in-card { cursor: pointer; }
.exp-in-card:hover { color: var(--green); }
.card-new { opacity: 0.4; transition: all 0.3s ease; }
.card-new:hover { opacity: 0.8; }
.card-inp {
  background: transparent; border: none; border-bottom: 1px solid rgba(79,232,124,0.2);
  color: var(--text); font: 18px var(--font-mono); outline: none; flex: 1; min-width: 0;
}
.card-inp:focus { border-bottom-color: var(--green); }
.dim { color: var(--text-dim); }
.hint { margin-top: 8px; }

/* ── Side panel ────────────────────────────────────────────────── */
.side-panel { width: 30ch; flex-shrink: 0; border-right: 2px solid var(--border-solid); padding-right: 1ch; }
.side-list { margin: 4px 0; }
.exp-item { font-size: 18px; padding: 2px 0; cursor: pointer; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: all 0.15s ease; }
.exp-item:hover { color: var(--text); padding-left: 2px; }
.exp-item.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }
.side-inp {
  background: transparent; border: none; border-bottom: 1px solid rgba(79,232,124,0.15);
  color: var(--text); font: 18px var(--font-mono); outline: none; width: 24ch;
}
.side-inp::placeholder { color: var(--text-dim); }
.cmd-line { font-size: 18px; padding: 1px 0; }
.back-link { cursor: pointer; margin-top: 6px; }
.back-link:hover { color: var(--green); }
.archive-btn { color: var(--text-dim); font-size: 10px; cursor: pointer; opacity: 0; transition: opacity 0.15s; }
.ascii-card:hover .archive-btn, .exp-item:hover .archive-btn { opacity: 0.6; }
.archive-btn:hover { opacity: 1 !important; color: var(--red); }
.desc { max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
.creating { color: var(--amber); animation: pulse 1s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
</style>
