<script setup>
import { ref, watch, computed, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  server: { type: Object, default: null },
});
const emit = defineEmits(["close"]);

const { loadServerJobs, loadExperimentTrials } = useFirestore();

const jobs = ref([]);            // active jobs claimed by this server
const recent = ref([]);          // finished jobs claimed by this server
const trialsByJob = ref({});     // jobId -> {list, claimedBy, ...}
const loading = ref(false);
const lastLoad = ref(0);

const now = ref(Date.now());
const tick = setInterval(() => { now.value = Date.now(); }, 1000);
onUnmounted(() => clearInterval(tick));

watch(() => props.server, async (s) => {
  jobs.value = [];
  recent.value = [];
  trialsByJob.value = {};
  if (!s || !s.id) return;
  loading.value = true;
  try {
    const all = await loadServerJobs(s.id);
    jobs.value = all.filter(j => ["claimed", "running"].includes(j.status));
    recent.value = all.filter(j => !["claimed", "running"].includes(j.status)).slice(0, 5);
    for (const j of jobs.value) {
      if (j.study_id && j.experiment_code) {
        trialsByJob.value[j.id] = await loadExperimentTrials(j.study_id, j.experiment_code);
      }
    }
    lastLoad.value = now.value;
  } finally {
    loading.value = false;
  }
}, { immediate: true });

function fmtTime(d) {
  if (!d) return "-";
  const t = d.toDate ? d.toDate() : new Date(d);
  return t.toLocaleString("sv").replace("T", " ").slice(0, 16);
}

function elapsed(s) {
  if (!s) return "-";
  const t = s.toDate ? s.toDate().getTime() : new Date(s).getTime();
  const sec = Math.floor((now.value - t) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  return `${Math.floor(sec / 3600)}h`;
}

const statusIcon = { queued: "○", claimed: "◐", running: "●", completed: "✓", failed: "✗", cancelled: "⊘" };
const statusCls  = { queued: "a", claimed: "g", running: "g", completed: "g", failed: "r", cancelled: "r" };
const trialIcon = { pending: "·", running: "●", completed: "✓", error: "✗" };
const trialCls  = { pending: "dim", running: "g", completed: "g", error: "r" };

const serverStatus = computed(() => {
  const s = props.server;
  if (!s) return { text: "?", cls: "dim" };
  if (!s.last_seen) return { text: "offline", cls: "r" };
  const interval = (s.heartbeat_interval_sec || 30) * 1000;
  const last = s.last_seen.toDate ? s.last_seen.toDate().getTime() : Date.parse(s.last_seen);
  if (isNaN(last)) return { text: "offline", cls: "r" };
  if (now.value - last > interval * 2 + 15000) return { text: "offline", cls: "r" };
  return s.status === "busy" ? { text: "busy", cls: "a" } : { text: "online", cls: "g" };
});

function jobTrials(j) {
  const t = trialsByJob.value[j.id];
  return t || { list: [], claimedBy: {}, completedBy: {}, versions: {}, errors: {} };
}
</script>

<template>
  <Teleport to="body">
    <div v-if="server" class="popup-overlay" @click="emit('close')">
      <div class="popup" @click.stop>
        <TerminalCard :title="server.id + ' · ' + serverStatus.text" :min-width="90" :collapsible="false">
          <div class="server-detail">
            <div class="detail-row"><span class="k dim">status</span>
              <span :class="serverStatus.cls">{{ serverStatus.text }}</span>
              <span class="dim">· seen {{ fmtTime(server.last_seen) }}</span></div>
            <div class="detail-row"><span class="k dim">version</span>
              <span>{{ server.version || "-" }}</span>
              <span class="dim">· {{ server.jobs_completed || 0 }} jobs completed</span></div>
            <div class="detail-row"><span class="k dim">load</span>
              <span>cpu {{ server.cpu_percent != null ? Math.round(server.cpu_percent) + "%" : "-" }}</span>
              <span>mem {{ server.memory_percent != null ? Math.round(server.memory_percent) + "%" : "-" }}</span>
              <span v-if="server.gpu_percent != null">gpu {{ Math.round(server.gpu_percent) }}%</span></div>
            <div class="detail-row"><span class="k dim">render</span>
              <span>{{ server.render_active ? "relay active" : "-" }}</span>
              <span v-if="server.funnel_url" class="dim">{{ server.funnel_url }}</span></div>

            <div class="trials-hdr g">▸ handling now</div>
            <div v-if="loading" class="dim">loading…</div>
            <div v-else-if="!jobs.length" class="dim">(no active jobs — server is idle)</div>
            <div v-for="j in jobs" :key="j.id" class="job-block">
              <div class="job-line">
                <span :class="statusCls[j.status]">{{ statusIcon[j.status] || "?" }} {{ j.status }}</span>
                <span class="dim">{{ j.id }}</span>
                <span class="dim">{{ j.study_id }}/{{ j.experiment_code }}</span>
                <span class="g">{{ j.status === "running" && j.started_at ? elapsed(j.started_at) : elapsed(j.claimed_at) }}</span>
                <span class="dim">{{ j.result?.trials_completed ?? j.result?.games_completed ?? 0 }}/{{ j.result?.trial_count ?? "?" }} trials</span>
              </div>
              <div class="trial-strip">
                <span v-for="(s, i) in jobTrials(j).list" :key="i" class="trial-chip"
                  :class="[trialCls[s] || 'dim', jobTrials(j).claimedBy[i] === server.id ? 'mine' : '']"
                  :title="'trial ' + i + ' — claimed by ' + (jobTrials(j).claimedBy[i] || '?')">
                  {{ trialIcon[s] || "?" }}{{ i }}
                </span>
                <span v-if="!jobTrials(j).list.length" class="dim">(no trials yet)</span>
              </div>
            </div>

            <template v-if="recent.length">
              <div class="trials-hdr dim">▸ recent by this server</div>
              <div v-for="j in recent" :key="j.id" class="job-line dim">
                <span :class="statusCls[j.status]">{{ statusIcon[j.status] || "?" }} {{ j.status }}</span>
                <span class="dim">{{ j.id }}</span>
                <span class="dim">{{ j.study_id }}/{{ j.experiment_code }}</span>
                <span>{{ fmtTime(j.finished_at) }}</span>
              </div>
            </template>

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
.popup::-webkit-scrollbar { width: var(--scrollbar-w, 3px); }
.popup::-webkit-scrollbar-thumb { background: var(--border); border-radius: var(--radius-sm); }
.popup::-webkit-scrollbar-track { background: transparent; }

.server-detail {
  font-family: var(--font-mono); font-size: var(--fs-base); line-height: var(--lh-loose);
  display: flex; flex-direction: column; gap: var(--sp-xxs);
}
.detail-row { display: flex; gap: var(--sp-md); }
.k { min-width: 8ch; }
.trials-hdr { margin-top: var(--sp-sm); }
.job-block {
  margin: var(--sp-xxs) 0; padding: var(--sp-xxs) var(--sp-sm);
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
  display: flex; flex-direction: column; gap: var(--sp-xxs);
}
.job-line { display: flex; gap: var(--sp-md); align-items: baseline; flex-wrap: wrap; }
.trial-strip { display: flex; gap: var(--sp-xxs); flex-wrap: wrap; }
.trial-chip { padding: 0 var(--sp-xxs); border-radius: var(--radius-sm); }
.trial-chip.mine { outline: 1px solid var(--green); }
.popup-acts { margin-top: var(--sp-sm); }
.pop-link { color: var(--text-dim); cursor: pointer; font-size: var(--fs-ui); }
.pop-link:hover { color: var(--green); }
</style>
