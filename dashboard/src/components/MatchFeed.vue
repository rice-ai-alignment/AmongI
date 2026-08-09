<script setup>
import { ref, computed } from "vue";
import AsciiTable from "./AsciiTable.vue";

const props = defineProps({ games: Array });

const DEFAULT_SHOW = 10;
const showAll = ref(false);

const columns = [
  { key: "ts",       header: "ended",       align: "left" },
  { key: "game_id",  header: "game",        align: "left" },
  { key: "winner",   header: "winner",      align: "left" },
  { key: "kills",    header: "k",           align: "right" },
  { key: "ejections",header: "e",           align: "right" },
  { key: "duration", header: "duration",    align: "left" },
];

function fmtDur(sec) {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  return `${m}m${Math.round(sec % 60)}s`;
}

function formatCell(key, value, row) {
  if (key === "winner") {
    const cls = value === "crewmates" ? "g" : value === "imposters" ? "r" : "a";
    return { text: value, cls };
  }
  return { text: value };
}

const allGames = computed(() => {
  return [...(props.games || [])].reverse().map(g => ({
    ts:        g.ended_at ? new Date(g.ended_at).toISOString().slice(0, 16).replace("T", " ") : "?",
    game_id:   g.game_id || "?",
    winner:    g.winner || "?",
    kills:     String(g.kills || 0),
    ejections: String(g.ejections || 0),
    duration:  fmtDur(g.duration_sec),
  }));
});

const rows = computed(() => {
  return showAll.value ? allGames.value : allGames.value.slice(0, DEFAULT_SHOW);
});

const hidden = computed(() => Math.max(0, allGames.value.length - DEFAULT_SHOW));
</script>

<template>
  <div>
    <AsciiTable
      title="match log"
      :columns="columns"
      :rows="rows"
      :formatCell="formatCell"
      :minWidth="66"
    />
    <div v-if="hidden > 0" class="expand-row">
      <span class="expand-link" @click="showAll = !showAll">
        [ {{ showAll ? 'collapse' : 'show all (' + hidden + ' more)' }} ]
      </span>
    </div>
  </div>
</template>

<style scoped>
.expand-row {
  padding: var(--sp-xxs) var(--sp-md);
}
.expand-link {
  font-size: var(--fs-sm); color: var(--text-dim); cursor: pointer;
}
.expand-link:hover { color: var(--text); }
</style>
