<script setup>
import { ref, computed } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";
import TypedLines from "./TypedLines.vue";

const { games, activeStudyId, activeExperimentId, loadGameTrace } = useFirestore();

const selectedGame = ref(null);
const selectedGameIndex = ref(-1);
const traceRaw = ref("");
const traceParsed = ref([]);
const traceLoading = ref(false);
const viewMode = ref("readable"); // "readable" | "raw"
const expandedEvent = ref(null);  // parsed trace event shown in the detail popup

const gameList = computed(() =>
  (games.value || []).map((g, i) => ({
    index: i,
    id: g.game_id || `game-${i + 1}`,
    winner: g.winner || "?",
    kills: g.kills || 0,
    ejections: g.ejections || 0,
    duration: g.duration_sec ? `${Math.round(g.duration_sec / 60)}m` : "?",
    raw: g,
  }))
);

function selectGame(g) {
  selectedGame.value = g;
  selectedGameIndex.value = g.index;
  traceRaw.value = "";
  traceParsed.value = [];
  viewMode.value = "readable";
  expandedEvent.value = null;
}

function parseTrace(raw) {
  const lines = [];
  const traceStr = String(raw);
  // Try splitting on newlines, handling both JSONL and pretty-printed
  const blocks = traceStr.split(/\n(?=\{|\n\{)/);
  for (const block of blocks) {
    const trimmed = block.trim();
    if (!trimmed) continue;
    try {
      const ev = JSON.parse(trimmed);
      const ts = ev.elapsed_ms != null ? (ev.elapsed_ms / 1000).toFixed(1) + "s" : "";
      const cat = ev.category || "";
      const type = ev.type || "";
      const actor = ev.actor || ev.agent || "";
      let detail = "";
      if (ev.actions && Array.isArray(ev.actions)) {
        detail = ev.actions.map(a => {
          if (a.type === "kill") return `kill: ${a.killer || "?"} → ${a.victim || "?"}`;
          if (a.type === "report") return `report: ${a.reporter || "?"} reported ${a.victim || "?"}`;
          if (a.type === "move") return `move: ${JSON.stringify(a.from)} → ${JSON.stringify(a.to)}`;
          if (a.type === "say") return `say: "${(a.message || "").slice(0, 40)}"`;
          if (a.type === "vote") return `vote: ${a.voted_for || "?"}`;
          return a.type || "?";
        }).join("; ");
      } else if (type === "game_start") detail = "GAME START";
      else if (type === "game_end") detail = `GAME END winner=${ev.winner || ev.recap?.winner || "?"}`;
      else if (cat === "context") {
        const prompt = String(ev.prompt || "");
        detail = "context: " + prompt.replace(/\n/g, " ").slice(0, 80) + (prompt.length > 80 ? "…" : "");
      }
      else if (cat === "decision") {
        detail = "decision: " + JSON.stringify(ev.decision || {}).slice(0, 100);
      }
      else if (cat === "system") detail = type;
      const color = type === "kill" ? "r" : type === "report" ? "a" : type === "game_end" ? "g" : "";
      const expandable = cat === "context" || cat === "decision";
      lines.push({ ts, cat, actor, detail, color, expandable, raw: ev });
    } catch {
      if (trimmed.length > 5) lines.push({ ts: "", cat: "", actor: "", detail: trimmed.slice(0, 120), color: "dim", expandable: false, raw: trimmed });
    }
  }
  return lines;
}

async function loadTrace() {
  if (!selectedGame.value || !activeStudyId.value || !activeExperimentId.value) return;
  traceLoading.value = true;
  try {
    const gid = selectedGame.value.id;
    const raw = await loadGameTrace(activeStudyId.value, activeExperimentId.value, gid);
    if (raw) {
      traceRaw.value = String(raw);
      traceParsed.value = parseTrace(raw);
    } else {
      // No trace file — show recap as raw
      traceRaw.value = JSON.stringify(selectedGame.value.raw, null, 2);
      traceParsed.value = [];
    }
  } catch (e) {
    traceRaw.value = "Failed to load: " + e.message;
    traceParsed.value = [];
  } finally {
    traceLoading.value = false;
  }
}
</script>

<template>
  <div class="inspector">
    <!-- Trial selector — compact top bar -->
    <TerminalCard title="trials" :min-width="24" :collapsible="true">
      <div class="trial-bar">
        <div v-if="!gameList.length" class="dim">(no game data)</div>
        <div
          v-for="g in gameList" :key="g.id"
          class="trial-chip"
          :class="{ active: selectedGameIndex === g.index }"
          @click="selectGame(g); loadTrace()"
        >
          <span class="dim">{{ g.id }}</span>
          <span :class="g.winner === 'timeout' ? 'a' : g.winner === 'token_limit' ? 'r' : 'g'">
            {{ g.winner }}
          </span>
          <span class="dim">{{ g.duration }} · {{ g.kills }}k</span>
        </div>
      </div>
    </TerminalCard>

    <!-- Trace/log viewer -->
    <div class="trace-main">
      <div v-if="!selectedGame" class="dim" style="padding:var(--sp-md)">
        select a trial from the list above to view its trace
      </div>

      <template v-else>
        <!-- Meta bar -->
        <div class="trace-meta">
          <span class="dim">{{ selectedGame.id }}</span>
          <span :class="selectedGame.winner === 'timeout' ? 'a' : 'g'">
            winner: <b>{{ selectedGame.winner }}</b>
          </span>
          <span class="dim">{{ selectedGame.kills }} kills · {{ selectedGame.ejections }} ejections · {{ selectedGame.duration }}</span>
          <span class="spacer"></span>
          <span class="tab" :class="{ active: viewMode === 'readable' }" @click="viewMode = 'readable'">[ readable ]</span>
          <span class="tab" :class="{ active: viewMode === 'raw' }" @click="viewMode = 'raw'">[ raw ]</span>
        </div>

        <!-- Readable view -->
        <div v-if="viewMode === 'readable'" class="trace-body">
          <div v-if="traceLoading" class="dim">loading...</div>
          <div v-else-if="traceParsed.length">
            <div
              v-for="(ev, i) in traceParsed" :key="i"
              class="trace-line"
              :class="{ clickable: ev.expandable }"
              @click="ev.expandable && (expandedEvent = ev)"
            >
              <span class="dim">{{ ev.ts.padStart(7) }}</span>
              <span class="dim">{{ ev.cat.padEnd(9) }}</span>
              <span>{{ ev.actor.padEnd(10) }}</span>
              <span :class="ev.color" class="line-detail">{{ ev.detail }}</span>
              <span v-if="ev.expandable" class="a">▸</span>
            </div>
          </div>
          <div v-else class="dim">no parsed events — switch to [ raw ] view</div>
        </div>

        <!-- Raw view -->
        <pre v-else class="trace-raw">{{ traceRaw }}</pre>
      </template>
    </div>

    <!-- Detail popup — full context / decision, no horizontal scroll -->
    <div v-if="expandedEvent" class="popup-overlay" @click="expandedEvent = null">
      <div class="popup" @click.stop>
        <TerminalCard
          :title="expandedEvent.cat + ' · ' + expandedEvent.actor"
          :min-width="100"
          :collapsible="false"
        >
          <div class="detail-popup">
            <template v-if="expandedEvent.raw.prompt">
              <div class="g detail-hdr">▸ prompt</div>
              <TypedLines :text="expandedEvent.raw.prompt" clazz="detail-block" />
            </template>
            <template v-if="expandedEvent.raw.action_schema">
              <div class="g detail-hdr">▸ action schema</div>
              <TypedLines :text="JSON.stringify(expandedEvent.raw.action_schema, null, 2)" clazz="detail-block" />
            </template>
            <template v-if="expandedEvent.raw.context_channels">
              <div class="g detail-hdr">▸ context channels</div>
              <TypedLines :text="JSON.stringify(expandedEvent.raw.context_channels, null, 2)" clazz="detail-block" />
            </template>
            <template v-if="expandedEvent.raw.api_messages">
              <div class="g detail-hdr">▸ api messages</div>
              <TypedLines :text="JSON.stringify(expandedEvent.raw.api_messages, null, 2)" clazz="detail-block" />
            </template>
            <template v-if="expandedEvent.raw.decision">
              <div class="g detail-hdr">▸ decision</div>
              <TypedLines :text="JSON.stringify(expandedEvent.raw.decision, null, 2)" clazz="detail-block" />
            </template>
            <div class="popup-acts">
              <span class="pop-link" @click="expandedEvent = null">[ close ]</span>
            </div>
          </div>
        </TerminalCard>
      </div>
    </div>
  </div>
</template>

<style scoped>
.inspector { display: flex; flex-direction: column; gap: var(--sp-sm); flex: 1; min-height: 0; }
.trace-main { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow-y: auto; overflow-x: hidden; }

/* Trial selector top bar */
.trial-bar {
  display: flex; flex-wrap: wrap; gap: var(--sp-sm);
  align-items: center;
}
.trial-chip {
  display: flex; gap: var(--sp-xs); align-items: baseline;
  font-size: var(--fs-base); padding: 2px var(--sp-xs); cursor: pointer;
  border: var(--border-hair); border-radius: var(--radius-sm);
  background: var(--surface-2);
}
.trial-chip:hover { color: var(--text); }
.trial-chip.active { color: var(--green); text-shadow: 0 0 4px rgba(79,232,124,0.2); border-color: var(--green); }

.trace-meta {
  display: flex; align-items: baseline; gap: var(--sp-sm);
  font-size: var(--fs-sm); padding-bottom: var(--sp-xs);
  border-bottom: var(--border-hair); margin-bottom: var(--sp-xs); flex-shrink: 0;
}
.tab { font-size: var(--fs-sm); color: var(--text-dim); cursor: pointer; }
.tab:hover  { color: var(--text); }
.tab.active { color: var(--green); }

.trace-body {
  font-family: var(--font-mono); font-size: var(--fs-base); line-height: 1.5;
  flex: 1; overflow-y: auto; overflow-x: hidden; min-height: 0;
}
.trace-line {
  display: flex; gap: var(--sp-xs); align-items: baseline;
  padding: 2px 0; white-space: nowrap;
  border-bottom: var(--border-hair);
}
.trace-line.clickable { cursor: pointer; }
.trace-line.clickable:hover { color: var(--text); }
.line-detail {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  flex: 1; min-width: 0;
}
.trace-raw {
  font-family: var(--font-mono); font-size: var(--fs-base); line-height: 1.5;
  color: var(--text-dim); white-space: pre-wrap; word-break: break-word;
  flex: 1; overflow-y: auto; overflow-x: hidden; margin: 0;
}

/* ── Detail popup ───────────────────────────────────────────── */
.popup-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.popup {
  /* Hug the card so clicks outside it land on the overlay (→ close) */
  width: fit-content; max-width: min(95vw, 1500px);
  max-height: 85vh;
  overflow-y: auto; overflow-x: hidden;
}
.popup > * { max-width: 100%; }
.detail-popup {
  font-family: var(--font-mono); font-size: var(--fs-base);
}
.detail-hdr {
  font-size: var(--fs-base); margin: var(--sp-xs) 0 var(--sp-xxs);
}
/* Blocks flow at full height — the popup itself is the ONLY scroller,
   so there's one themed scrollbar instead of nested ones with gaps. */
.detail-block {
  display: block;
  font-family: var(--font-mono); font-size: var(--fs-base); line-height: 1.5;
  color: var(--text-dim); white-space: pre-wrap; word-break: break-word;
  overflow-wrap: anywhere;
  margin: 0 0 var(--sp-xs); padding: var(--sp-xxs) var(--sp-xs);
  background: var(--bg-deep); border-radius: var(--radius-sm);
}
.popup-acts {
  display: flex; justify-content: center; margin-top: var(--sp-sm);
}
.pop-link { color: var(--text-dim); cursor: pointer; font-size: var(--fs-ui); }
.pop-link:hover { color: var(--green); }

/* Themed scrollbars for the popup and the trace pane */
.popup::-webkit-scrollbar,
.trace-raw::-webkit-scrollbar { width: var(--scrollbar-w, 3px); }
.popup::-webkit-scrollbar-thumb,
.trace-raw::-webkit-scrollbar-thumb {
  background: var(--border); border-radius: var(--radius-sm);
}
.popup::-webkit-scrollbar-track,
.trace-raw::-webkit-scrollbar-track { background: transparent; }
</style>
