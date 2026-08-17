<script setup>
import { ref, computed, watch } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";

const { games } = useFirestore();

// ── Graph config ──────────────────────────────────────────────────
const graphType = ref("bar");
const xField = ref("winner");
const yField = ref("count");
const groupBy = ref("");

const graphTypes = [
  { key: "bar", label: "hbar" },
  { key: "vbar", label: "vbar" },
  { key: "line", label: "line" },
  { key: "stacked", label: "stacked" },
];

// Discover available fields from game data
const fields = computed(() => {
  const sample = games.value[0] || {};
  const f = [
    { key: "winner", label: "winner", kind: "cat" },
    { key: "kills", label: "kills", kind: "num" },
    { key: "ejections", label: "ejections", kind: "num" },
    { key: "duration_sec", label: "duration", kind: "num" },
    { key: "game_index", label: "game #", kind: "seq" },
  ];
  // Per-player fields
  const players = sample.players;
  if (players && players.length) {
    const p0 = players[0] || {};
    if (p0.role != null) f.push({ key: "player.role", label: "player role", kind: "cat" });
    if (p0.name != null) f.push({ key: "player.name", label: "player name", kind: "cat" });
    if (p0.kills != null) f.push({ key: "player.kills", label: "player kills", kind: "num" });
    if (p0.wins != null) f.push({ key: "player.wins", label: "player wins", kind: "num" });
  }
  return f;
});

const groupFields = computed(() =>
  fields.value.filter(f => f.kind === "cat")
);

// ── Resolve value from a game doc ──────────────────────────────────
function resolve(game, field, index) {
  if (!field) return null;
  if (field === "count") return 1;
  if (field === "game_index") return game.game_index ?? (index ?? 0) + 1;
  if (field.startsWith("player.")) {
    const sub = field.slice(7);
    return (game.players || []).map(p => p[sub] ?? null).filter(v => v != null);
  }
  return game[field] ?? null;
}

// ── Build chart data ──────────────────────────────────────────────
const chartData = computed(() => {
  if (!games.value.length) return { type: "empty" };

  if (graphType.value === "bar" || graphType.value === "vbar") {
    const buckets = {};
    games.value.forEach((g, i) => {
      let xvals = resolve(g, xField.value, i);
      if (!Array.isArray(xvals)) xvals = [xvals];
      const yval = yField.value === "count" ? 1 : (resolve(g, yField.value, i) ?? 0);
      for (const x of xvals) {
        const key = String(x ?? "?");
        buckets[key] = (buckets[key] || 0) + (typeof yval === "number" ? yval : 1);
      }
    });
    return { type: "bar", buckets, total: games.value.length };
  }

  if (graphType.value === "line") {
    const points = games.value.map((g, i) => {
      const yRaw = yField.value === "count" ? 1 : (resolve(g, yField.value, i) ?? 0);
      const yVal = Array.isArray(yRaw) ? yRaw.length : (typeof yRaw === "number" ? yRaw : Number(yRaw) || 0);
      return { x: i + 1, y: yVal, label: `g${i + 1}` };
    });
    return { type: "line", points };
  }

  if (graphType.value === "stacked") {
    const groups = {};
    const allKeys = new Set();
    games.value.forEach((g, i) => {
      const gk = String(resolve(g, groupBy.value || xField.value, i) ?? "?");
      const xk = String(resolve(g, xField.value, i) ?? "?");
      if (!groups[gk]) groups[gk] = {};
      groups[gk][xk] = (groups[gk][xk] || 0) + 1;
      allKeys.add(xk);
    });
    return { type: "stacked", groups, keys: [...allKeys] };
  }

  return { type: "empty" };
});

// ── Render ────────────────────────────────────────────────────────
const MAX_BAR = 36;
const MAX_H = 16;
const COLORS = ["g", "r", "c-d3", "c-d4", "a", "c-d5", "c-d6", "c-d2"];
const LINE_CHARS = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];

const chartLines = computed(() => {
  const d = chartData.value;
  if (d.type === "empty") return [];

  // ── Horizontal bar ───────────────────────────────────────────
  if (d.type === "bar") {
    const entries = Object.entries(d.buckets).sort((a, b) => b[1] - a[1]);
    const maxVal = Math.max(...entries.map(e => e[1]), 1);
    return entries.map(([key, val], i) => {
      const n = Math.round((val / maxVal) * MAX_BAR);
      const bar = "█".repeat(n);
      const cls = COLORS[i % COLORS.length];
      return { line: ` <span class="${cls}">${key.padEnd(14)} │${bar}</span> <b>${val}</b>` };
    });
  }

  // ── Vertical bar ─────────────────────────────────────────────
  if (d.type === "vbar") {
    const entries = Object.entries(d.buckets).sort((a, b) => b[1] - a[1]);
    const maxVal = Math.max(...entries.map(e => e[1]), 1);
    const lines = [];
    // Build from top down
    for (let row = MAX_H; row > 0; row--) {
      let line = "  ";
      for (let i = 0; i < entries.length; i++) {
        const val = entries[i][1];
        const h = Math.round((val / maxVal) * MAX_H);
        const cls = COLORS[i % COLORS.length];
        if (h >= row) line += `<span class="${cls}">█ </span>`;
        else line += `<span class="dim">· </span>`;
      }
      if (row === MAX_H) line += ` ${maxVal}`;
      lines.push({ line });
    }
    // Labels
    let labelLine = "  ";
    for (let i = 0; i < entries.length; i++) {
      labelLine += `<span class="dim">${entries[i][0].slice(0, 2)}</span> `;
    }
    lines.push({ line: labelLine });
    return lines;
  }

  // ── Line (sparkline using Unicode block chars) ───────────────
  if (d.type === "line") {
    const maxY = Math.max(...d.points.map(p => p.y), 1);
    // Build a canvas-like grid then render
    const grid = [];
    for (let row = 0; row <= MAX_H; row++) {
      grid.push(new Array(d.points.length).fill(" "));
    }
    for (let i = 0; i < d.points.length; i++) {
      const y = d.points[i].y;
      if (typeof y !== "number" || isNaN(y)) continue;
      const h = Math.round((y / maxY) * MAX_H);
      const row = MAX_H - h;
      if (row >= 0 && row < grid.length) grid[row][i] = "█";
    }
    const lines = [];
    for (let row = 0; row <= MAX_H; row++) {
      const label = row === MAX_H ? `${maxY}`.padStart(3) : row === 0 ? "  0" : "   ";
      lines.push({ line: `${label} │${grid[row].join("")}` });
    }
    // X-axis labels
    const xLabels = d.points.map(p => p.label);
    lines.push({ line: `     ${"─".repeat(d.points.length * 2)}` });
    lines.push({ line: `     ${xLabels.map(l => l.slice(0,2).padStart(2)).join(" ")}` });
    return lines;
  }

  // ── Stacked bars ─────────────────────────────────────────────
  if (d.type === "stacked") {
    const lines = [];
    let ci = 0;
    for (const [group, buckets] of Object.entries(d.groups)) {
      const cls = COLORS[ci % COLORS.length]; ci++;
      lines.push({ line: ` <span class="${cls}"><b>${group}</b></span>` });
      for (const key of d.keys) {
        const val = buckets[key] || 0;
        const n = Math.max(1, val);
        lines.push({ line: `   <span class="dim">${key.padEnd(12)}</span> <span class="${cls}">${"█".repeat(n)}</span>  <b>${val}</b>` });
      }
    }
    return lines;
  }

  return [];
});
</script>

<template>
  <div class="data-viewer">
    <!-- Controls -->
    <TerminalCard title="graph builder" :min-width="60" :collapsible="false">
      <div class="controls">
        <div class="ctrl-row">
          <span class="dim">type:</span>
          <span v-for="gt in graphTypes" :key="gt.key"
            class="tab" :class="{ active: graphType === gt.key }"
            @click="graphType = gt.key">[ {{ gt.label }} ]</span>
        </div>
        <div class="ctrl-row">
          <span class="dim">x:</span>
          <select v-model="xField" class="ctrl-sel">
            <option v-for="f in fields" :key="f.key" :value="f.key">{{ f.label }}</option>
          </select>
          <span class="dim">y:</span>
          <select v-model="yField" class="ctrl-sel">
            <option value="count">count</option>
            <option v-for="f in fields.filter(f2 => f2.kind === 'num' && !f2.key.startsWith('player.'))" :key="f.key" :value="f.key">{{ f.label }}</option>
          </select>
          <template v-if="graphType === 'stacked'">
            <span class="dim">group:</span>
            <select v-model="groupBy" class="ctrl-sel">
              <option value="">(none)</option>
              <option v-for="f in groupFields" :key="f.key" :value="f.key">{{ f.label }}</option>
            </select>
          </template>
        </div>
      </div>
    </TerminalCard>

    <!-- Chart -->
    <TerminalCard v-if="chartLines.length" title="chart" :min-width="60" :collapsible="false">
      <div v-for="(b, i) in chartLines" :key="i" class="chart-line" v-html="b.line"></div>
    </TerminalCard>
    <TerminalCard v-else title="chart" :min-width="40">
      <div class="dim">({{ games.length ? 'nothing to plot' : 'no data — run the experiment first' }})</div>
    </TerminalCard>
  </div>
</template>

<style scoped>
.data-viewer { display: flex; flex-direction: column; gap: var(--sp-sm); }
.controls { display: flex; flex-direction: column; gap: var(--sp-xs); }
.ctrl-row {
  display: flex; align-items: center; gap: var(--sp-sm);
  font-size: var(--fs-ui);
}
.tab { font-size: var(--fs-sm); color: var(--text-dim); cursor: pointer; }
.tab:hover  { color: var(--text); }
.tab.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }
.ctrl-sel {
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
  color: var(--text); font: var(--fs-base) var(--font-mono);
  padding: 1px var(--sp-xs); outline: none; cursor: pointer;
}
.ctrl-sel:focus { border-color: var(--green); }
.ctrl-sel option { background: var(--surface-2); }
.chart-line {
  font-size: var(--fs-base); line-height: var(--lh-tight);
  white-space: pre;
}
</style>
