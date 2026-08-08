<script setup>
import { computed } from "vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  config: { type: Object, default: null },
  title: { type: String, default: "config" },
});

const N = 7;

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function fmtVal(v) {
  if (v === null || v === undefined) return '<span class="c-lit">null</span>';
  if (typeof v === "boolean") return `<span class="c-num">${v}</span>`;
  if (typeof v === "number") return `<span class="c-num">${v}</span>`;
  if (typeof v === "string") {
    const s = esc(v);
    if (s.length > 64) return `<span class="c-lit">"${s.slice(0, 61)}..."</span>`;
    return `<span class="c-lit">"${s}"</span>`;
  }
  return esc(String(v));
}

function isCondition(n) { return n && n.type === "Condition"; }
function isExpression(n) { return n && n.type === "Value"; }
function isObjectNode(n) { return n && typeof n === "object" && !Array.isArray(n) && !isCondition(n) && !isExpression(n); }

function fmtExpr(node) {
  if (!node || typeof node !== "object") return fmtVal(node);
  const c = node.class;
  if (c === "Literal") return fmtVal(node.value);
  if (c === "VariableRef") return `<span class="c-var">${esc(node.path || "")}</span>`;
  if (c === "FunctionCall") {
    const args = (node.args || []).map(a => fmtExpr(a)).join(", ");
    return `<span class="c-fn">${esc(node.function || "")}</span>(${args})`;
  }
  return esc(JSON.stringify(node).slice(0, 40));
}

function fmtCond(node) {
  if (!node || typeof node !== "object") return esc(String(node));
  const c = node.class;
  if (c === "Comparison") {
    const l = node.left ? fmtExpr(node.left) : "?";
    const r = node.right ? fmtExpr(node.right) : "?";
    return `${l} <span class="c-op">${esc(node.op || "==")}</span> ${r}`;
  }
  if (c === "AgentCountCheck") {
    return `<span class="c-var">${esc(node.agent_type || "?")}</span> <span class="c-op">${esc(node.op || "==")}</span> ${fmtVal(node.count)}`;
  }
  if (c === "AgentTypeCheck") return `agent is <span class="c-var">${esc(node.agent_type || "?")}</span>`;
  if (c === "And" || c === "Or") {
    const parts = (node.conditions || []).map(cc => fmtCond(cc));
    const sep = c === "And" ? " <span class=\"c-op\">&&</span> " : " <span class=\"c-warn\">||</span> ";
    return "(" + parts.join(sep) + ")";
  }
  if (c === "Not") return "<span class=\"c-err\">not</span> (" + fmtCond(node.condition) + ")";
  if (c === "IsTruthy") return fmtExpr(node.value);
  return esc(c || "condition");
}

function colorClass(idx) { return `c-d${idx.rev % N}`; }
function nextColor(idx) { const c = colorClass(idx); idx.rev++; return c; }

function typeLabel(val, clsOverride) {
  if (!isObjectNode(val)) {
    if (isCondition(val)) return fmtCond(val);
    if (isExpression(val)) return fmtExpr(val);
    return fmtVal(val);
  }
  if (val.type && val.class) {
    // clsOverride: caller already assigned a color for this object block
    const c = clsOverride || "";
    return `<span class="${c}">${esc(val.type)}</span>::<span class="${c}">${esc(val.class)}</span>`;
  }
  return esc(String(val));
}

function nonMeta(obj) {
  return Object.entries(obj).filter(([k]) => k !== "type" && k !== "class");
}

// prefix segments: [{text, cls}] — each │ segment retains its source's color.
function prefixHtml(segments) {
  return segments.map(s =>
    s.cls ? `<span class="${s.cls}">${s.text}</span>` : s.text
  ).join("");
}

function connHtml(conn, cls) {
  return `<span class="${cls}">${conn}</span>`;
}

// `blockCls` — color of the parent block (connectors & │ bars use this).
// `gidx` — global counter; only advances when entering a new object block.
function build(obj, preSegs, isLast, blockCls, gidx) {
  const lines = [];
  const entries = nonMeta(obj);

  for (let i = 0; i < entries.length; i++) {
    const [key, val] = entries[i];
    const last = i === entries.length - 1;
    const conn = last ? "└── " : "├── ";
    const childSegs = [...preSegs, { text: last ? "    " : "│   ", cls: last ? null : blockCls }];
    const pre = prefixHtml(preSegs);
    const cpre = prefixHtml(childSegs);
    const keyHtml = `<span class="${blockCls}"><b>${esc(key)}</b></span>`;

    if (Array.isArray(val)) {
      lines.push({
        cls: blockCls,
        html: `${pre}${connHtml(conn, blockCls)}${keyHtml} <span class="${blockCls}">[${val.length}]</span>`,
        delay: 8,
      });
      for (let j = 0; j < val.length; j++) {
        const item = val[j];
        const jlast = j === val.length - 1;
        const jconn = jlast ? "└── " : "├── ";
        const jSegs = [...childSegs, { text: jlast ? "    " : "│   ", cls: jlast ? null : blockCls }];

        if (isObjectNode(item)) {
          const tc = nextColor(gidx);
          lines.push({
            cls: tc,
            html: `${cpre}${connHtml(jconn, blockCls)}<span class="${tc}">[${j}]</span> ${typeLabel(item, tc)}`,
            delay: 4,
          });
          const inner = {};
          for (const [k, v] of nonMeta(item)) inner[k] = v;
          if (Object.keys(inner).length) {
            lines.push(...build(inner, jSegs, jlast, tc, gidx));
          }
        } else {
          lines.push({
            cls: blockCls,
            html: `${cpre}${connHtml(jconn, blockCls)}<span class="${blockCls}">[${j}]</span> ${typeLabel(item, gidx)}`,
            delay: 4,
          });
        }
      }
    } else if (isObjectNode(val)) {
      const tc = nextColor(gidx);
      const keySpan = `<span class="${tc}"><b>${esc(key)}</b></span>`;
      lines.push({
        cls: tc,
        html: `${pre}${connHtml(conn, blockCls)}${keySpan} ${typeLabel(val, tc)}`,
        delay: 8,
      });
      const inner = {};
      for (const [k, v] of nonMeta(val)) inner[k] = v;
      if (Object.keys(inner).length) {
        lines.push(...build(inner, childSegs, last, tc, gidx));
      }
    } else {
      const txt = (val && typeof val === "object") ? typeLabel(val, gidx) : fmtVal(val);
      lines.push({ cls: blockCls, html: `${pre}${connHtml(conn, blockCls)}${keyHtml} ${txt}`, delay: 4 });
    }
  }
  return lines;
}

const lines = computed(() => {
  if (!props.config) return [];
  const gidx = { rev: 0 };
  const rootCls = nextColor(gidx);
  const rootHtml = props.config.type && props.config.class
    ? `<span class="${rootCls}">${esc(props.config.type)}</span>::<span class="${rootCls}">${esc(props.config.class)}</span>`
    : esc(props.config.type || props.config.class || "experiment");
  const inner = {};
  for (const [k, v] of Object.entries(props.config)) {
    if (k === "type" || k === "class") continue;
    inner[k] = v;
  }
  return [{ cls: rootCls, html: rootHtml, delay: 0 }, ...build(inner, [], true, rootCls, gidx)];
});
</script>

<template>
  <TerminalCard :title="title" :min-width="64" :collapsible="true" v-if="config">
    <div
      v-for="(line, i) in lines"
      :key="'l' + i"
      :class="['tree-line', line.cls]"
      v-html="' ' + line.html"
    ></div>
  </TerminalCard>
  <TerminalCard :title="title" :min-width="40" :collapsible="true" v-else>
    <div class="dim"><TypedSpan text=" (no config loaded)" :speed="TYPE.fast" /></div>
  </TerminalCard>
</template>

<style scoped>
.tree-line {
  white-space: pre;
  line-height: 1.45;
  font-size: 16px;
}
</style>
