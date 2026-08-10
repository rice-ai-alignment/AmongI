<script setup>
import { computed } from "vue";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";
import { TYPE } from "../composables/typeSettings.js";

const props = defineProps({
  title: { type: String, default: "" },
  /**
   * Column definitions.
   * { key: string, header: string, align?: 'left' | 'right' }
   */
  columns: { type: Array, default: () => [] },
  /**
   * Row data objects. Each row must have keys matching column definitions.
   */
  rows: { type: Array, default: () => [] },
  /**
   * Optional cell formatter.
   * (key, value, row) => { text: string, cls?: string, style?: string, bold?: boolean }
   * `text` is the raw string used for width calculation and display.
   */
  formatCell: { type: Function, default: null },
  emptyText: { type: String, default: "(no data)" },
  typeSpeed: { type: Number, default: 0 },
  minWidth: { type: Number, default: 50 },
  /** Milliseconds delay per row for staggered typing. */
  rowDelay: { type: Number, default: 120 },
  collapsible: { type: Boolean, default: true },
  /** Skip TypedSpan for data rows — renders instantly (for live-updating data). */
  noType: { type: Boolean, default: false },
});

const speed = computed(() => props.typeSpeed || TYPE.fast);

const table = computed(() => {
  const cols = props.columns;
  if (!cols.length) return null;

  // ---- compute max width per column (header included) ----
  const widths = Object.fromEntries(cols.map(c => [c.key, c.header.length]));

  const fmt = props.formatCell;
  for (const row of props.rows) {
    for (const col of cols) {
      const cell = fmt ? fmt(col.key, row[col.key], row) : { text: String(row[col.key] ?? "") };
      if (cell.text.length > widths[col.key]) widths[col.key] = cell.text.length;
    }
  }

  // ---- build header line ----
  const headerParts = cols.map(col =>
    col.align === "right"
      ? col.header.padStart(widths[col.key])
      : col.header.padEnd(widths[col.key])
  );
  const headerLine = `  <span class="tbl-hdr"><b>${headerParts.join("  ")}</b></span>`;

  // ---- build data rows ----
  const dataRows = props.rows.map((row, i) => {
    const parts = cols.map(col => {
      const raw = row[col.key];
      const cell = fmt ? fmt(col.key, raw, row) : { text: String(raw ?? "") };
      const padded =
        col.align === "right"
          ? cell.text.padStart(widths[col.key])
          : cell.text.padEnd(widths[col.key]);

      // wrap in HTML if needed
      if (cell.bold && cell.style && cell.cls) {
        return `<span class="${cell.cls}" style="${cell.style}"><b>${padded}</b></span>`;
      }
      if (cell.bold && cell.style) {
        return `<span style="${cell.style}"><b>${padded}</b></span>`;
      }
      if (cell.bold && cell.cls) {
        return `<span class="${cell.cls}"><b>${padded}</b></span>`;
      }
      if (cell.style && cell.cls) {
        return `<span class="${cell.cls}" style="${cell.style}">${padded}</span>`;
      }
      if (cell.bold) return `<b>${padded}</b>`;
      if (cell.style) return `<span style="${cell.style}">${padded}</span>`;
      if (cell.cls) return `<span class="${cell.cls}">${padded}</span>`;
      return padded;
    });
    return { delay: i * props.rowDelay, line: `  ${parts.join("  ")}` };
  });

  const totalW =
    Object.values(widths).reduce((a, b) => a + b, 0) +
    (cols.length - 1) * 2 +
    24; // leading spaces + gutters + safety
  return { header: headerLine, rows: dataRows, width: Math.max(totalW, props.minWidth) };
});
</script>

<template>
  <TerminalCard :title="title" :min-width="table?.width || minWidth" :collapsible="collapsible">
    <div v-if="table && table.rows.length">
      <div class="tbl-header">
        <TypedSpan :text="table.header" :speed="speed + 5" />
      </div>
      <div v-for="r in table.rows" :key="r.delay">
        <TypedSpan v-if="!noType" :text="r.line" :speed="speed" :delay="r.delay" />
        <span v-else v-html="' ' + r.line"></span>
      </div>
    </div>
    <div v-else>
      <TypedSpan :text="' ' + emptyText" :speed="speed" />
    </div>
  </TerminalCard>
</template>

<style scoped>
.tbl-header {
  color: var(--text-dim);
  padding-bottom: var(--sp-xxs);
}
</style>
