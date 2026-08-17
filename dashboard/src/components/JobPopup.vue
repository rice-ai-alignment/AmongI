<script setup>
import { ref, watch } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  job: { type: Object, default: null },
});
const emit = defineEmits(["close"]);

const { loadExperimentTrials, requestJobRender, loadJob, user } = useFirestore();

const trials = ref(null);   // {list, claimedBy, completedBy, versions, errors}
const loadingTrials = ref(false);
const expandedError = ref(null);  // trial index whose full traceback is shown

const jobLive = ref(null);  // periodically re-fetched job doc (render info)
const requesting = ref(false);
const requestError = ref("");
let pollTimer = null;

watch(() => props.job, (j) => {
  trials.value = null;
  jobLive.value = j ? { ...j } : null;
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (j && j.study_id && j.experiment_code) {
    loadingTrials.value = true;
    loadExperimentTrials(j.study_id, j.experiment_code)
      .then(t => { trials.value = t; })
      .catch(() => { trials.value = { list: [], claimedBy: {}, completedBy: {}, versions: {}, errors: {} }; })
      .finally(() => { loadingTrials.value = false; });
  }
  if (j && ["claimed", "running"].includes(j.status)) {
    // Poll the job doc so the render link appears once the server
    // processes an expose-render request.
    pollTimer = setInterval(async () => {
      const fresh = await loadJob(j.id);
      if (fresh) jobLive.value = fresh;
    }, 5000);
  }
}, { immediate: true });

async function exposeRender() {
  if (!props.job) return;
  requesting.value = true;
  requestError.value = "";
  try {
    await requestJobRender(props.job.id);
  } catch (e) {
    requestError.value = e.message || String(e);
  } finally {
    requesting.value = false;
  }
}

const render = () => jobLive.value?.render || props.job?.render || null;
const renderWsUrl = () => {
  const r = render();
  if (!r) return null;
  if (r.url && r.url.startsWith("https://")) return "wss://" + r.url.slice(8);
  return null;
};

function fmtTime(d) {
  if (!d) return "-";
  const t = d.toDate ? d.toDate() : new Date(d);
  return t.toLocaleString("sv").replace("T", " ").slice(0, 16);
}

function cleanError(err) {
  if (!err) return "";
  return err.replace(/\s+/g, " ").trim();
}

const statusIcon = { queued: "○", claimed: "◐", running: "●", completed: "✓", failed: "✗", cancelled: "⊘" };
const statusCls  = { queued: "a", claimed: "g", running: "g", completed: "g", failed: "r", cancelled: "r" };

const trialIcon = { pending: "·", running: "●", completed: "✓", error: "✗" };
const trialCls  = { pending: "dim", running: "g", completed: "g", error: "r" };

const doneTrials = (j) => j.result?.trials_completed ?? j.result?.games_completed ?? "-";
const totalTrials = (j) => j.result?.trial_count ?? "-";
</script>

<template>
  <Teleport to="body">
    <div v-if="job" class="popup-overlay" @click="emit('close')">
      <div class="popup" @click.stop>
        <TerminalCard :title="job.id + ' · ' + job._status" :min-width="90" :collapsible="false">
          <div class="job-detail">
            <div class="detail-row"><span class="k dim">status</span>
              <span :class="statusCls[job._status]">{{ statusIcon[job._status] || "?" }} {{ job._status }}</span></div>
            <div class="detail-row"><span class="k dim">target</span>
              <span>{{ job.study_id }}/{{ job.experiment_code }}</span></div>
            <div class="detail-row"><span class="k dim">created</span>
              <span>{{ fmtTime(job.created_at) }} <span class="dim">by {{ job.created_by || "-" }}</span></span></div>
            <div class="detail-row"><span class="k dim">claimed</span>
              <span>{{ fmtTime(job.claimed_at) }} <span class="dim">by {{ job.claimed_by || "-" }}</span></span></div>
            <div class="detail-row"><span class="k dim">started</span>
              <span>{{ fmtTime(job.started_at) }}</span></div>
            <div class="detail-row"><span class="k dim">finished</span>
              <span>{{ fmtTime(job.finished_at) }}</span></div>
            <div class="detail-row"><span class="k dim">updated</span>
              <span>{{ fmtTime(job.updated_at) }}</span></div>
            <div class="detail-row"><span class="k dim">result</span>
              <span>{{ doneTrials(job) }}/{{ totalTrials(job) }} trials</span></div>

            <!-- Render exposure -->
            <div class="detail-row"><span class="k dim">render</span>
              <template v-if="render() && render().active">
                <span class="g">relay active</span>
                <a v-if="render().url" class="pop-link" :href="render().url" target="_blank" rel="noopener">
                  [ view render ↗ ]
                </a>
                <span v-else class="dim">ws :{{ render().port }} (no funnel url)</span>
              </template>
              <span v-else-if="jobLive && jobLive.render_requested" class="a">relay starting…</span>
              <span v-else-if="['claimed', 'running'].includes(job._status)" class="dim">not exposed</span>
              <span v-else class="dim">-</span>
            </div>
            <div v-if="renderWsUrl()" class="detail-row"><span class="k"></span>
              <span class="dim">godot web: <span class="a">{{ renderWsUrl() }}</span></span>
            </div>
            <div v-if="['claimed', 'running'].includes(job._status) && user" class="detail-row">
              <span class="k"></span>
              <span class="pop-link" @click="exposeRender">
                {{ requesting ? 'requesting…' : '[ expose render ]' }}
              </span>
            </div>
            <div v-if="requestError" class="r">{{ requestError }}</div>

            <template v-if="job.error">
              <div class="detail-row"><span class="k dim">error</span></div>
              <pre class="error-msg">{{ cleanError(job.error) }}</pre>
            </template>

            <div class="trials-hdr dim">experiment trials</div>
            <div v-if="loadingTrials" class="dim">loading…</div>
            <div v-else-if="trials && trials.list.length" class="trial-chips">
              <div v-for="(s, i) in trials.list" :key="i" class="trial-chip" :class="trialCls[s] || 'dim'">
                <span class="trial-idx">[{{ String(i).padStart(2, "0") }}]</span>
                <span>{{ trialIcon[s] || "?" }} {{ s }}</span>
                <span v-if="trials.claimedBy[i]" class="dim">by {{ trials.claimedBy[i] }}</span>
                <span v-if="trials.completedBy[i]" class="dim">done {{ trials.completedBy[i] }}</span>
                <span v-if="trials.versions[i]" class="dim">v{{ trials.versions[i] }}</span>
                <span v-if="trials.errors[i]" class="r err-link"
                      :title="cleanError(trials.errors[i])"
                      @click="expandedError = expandedError === i ? null : i">
                  ✗ {{ cleanError(trials.errors[i]).slice(0, 60) }}
                  <span class="dim">[{{ expandedError === i ? 'hide' : 'trace' }}]</span>
                </span>
              </div>
              <pre v-if="expandedError === i && trials.errors[i]" class="error-msg">{{ trials.errors[i] }}</pre>
            </div>
            <div v-else class="dim">(no trials recorded)</div>

            <div class="popup-acts">
              <span class="pop-link" @click="emit('close')">[ close ]</span>
            </div>
          </div>
        </TerminalCard>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.popup-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.popup {
  /* Hug the card so clicks outside it land on the overlay (→ close) */
  width: fit-content; max-width: min(95vw, 1200px);
  max-height: 85vh;
  overflow-y: auto; overflow-x: hidden;
}
.popup > * { max-width: 100%; }
/* Themed scrollbars — match the rest of the dashboard */
.popup::-webkit-scrollbar,
.trial-chips::-webkit-scrollbar,
.error-msg::-webkit-scrollbar { width: var(--scrollbar-w, 3px); }
.popup::-webkit-scrollbar-thumb,
.trial-chips::-webkit-scrollbar-thumb,
.error-msg::-webkit-scrollbar-thumb {
  background: var(--border); border-radius: var(--radius-sm);
}
.popup::-webkit-scrollbar-track,
.trial-chips::-webkit-scrollbar-track,
.error-msg::-webkit-scrollbar-track { background: transparent; }
.job-detail {
  font-family: var(--font-mono); font-size: var(--fs-base); line-height: var(--lh-loose);
  display: flex; flex-direction: column; gap: var(--sp-xxs);
}
.detail-row { display: flex; gap: var(--sp-md); }
.k { min-width: 8ch; }
.error-msg {
  margin: 0; padding: var(--sp-xxs) var(--sp-sm);
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
  color: var(--red); white-space: pre-wrap; word-break: break-word;
  font-size: var(--fs-sm); line-height: var(--lh-body);
  max-height: 200px; overflow-y: auto;
}
.err-link { cursor: pointer; }
.err-link:hover { text-decoration: underline; }
.trials-hdr { margin-top: var(--sp-sm); }
.trial-chips {
  display: flex; flex-wrap: wrap; gap: var(--sp-xxs) var(--sp-sm);
  padding: var(--sp-xxs) var(--sp-sm);
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
  max-height: 220px; overflow-y: auto;
}
.trial-chip { display: flex; gap: var(--sp-xxs); align-items: baseline; }
.trial-idx { color: var(--text-dim); }
.popup-acts { margin-top: var(--sp-sm); }
.pop-link { color: var(--text-dim); cursor: pointer; font-size: var(--fs-ui); }
.pop-link:hover { color: var(--green); }
</style>
