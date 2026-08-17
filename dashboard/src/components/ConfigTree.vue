<script setup>
import { ref, computed, onMounted, reactive } from "vue";
import TerminalCard from "./TerminalCard.vue";
import TypedSpan from "./TypedSpan.vue";
import { TYPE } from "../composables/typeSettings.js";

const props = defineProps({
  config: { type: Object, default: null },
  title: { type: String, default: "config" },
  editable: { type: Boolean, default: false },
});

const schemaMap = ref({});
const N = 7;

// ── Mouse-tracking tooltip ────────────────────────────────────────
const tip = reactive({
  visible: false,
  x: 0, y: 0,
  html: "",
  typeName: "",
  className: "",
  params: [],
  source: "",
});

let tipTimeout = null;

function showTip(e, line) {
  if (!line || !line.tooltip) return;
  clearTimeout(tipTimeout);
  tip.visible = true;
  tip.x = e.clientX + 14;
  tip.y = e.clientY + 14;
  tip.typeName = line.typeName || "";
  tip.className = line.className || "";
  tip.params = line.params || [];
  tip.source = line.source || "";
  tip.html = line.tooltip || "";
  tipTimeout = null;
}

function moveTip(e) {
  tip.x = e.clientX + 14;
  tip.y = e.clientY + 14;
}

function hideTip() {
  tipTimeout = setTimeout(() => { tip.visible = false; }, 150);
}

function cancelHide() {
  clearTimeout(tipTimeout);
}

onMounted(async () => {
  try {
    const res = await fetch("/schema.json");
    const schema = await res.json();
    const map = {};
    for (const [typeName, typeInfo] of Object.entries(schema)) {
      for (const [className, classInfo] of Object.entries(typeInfo.classes || {})) {
        const key = `${typeName}::${className}`;
        map[key] = {
          desc: classInfo.description && classInfo.description !== className
            ? classInfo.description : "",
          source: classInfo.source || "",
          params: classInfo.params || {},
        };
      }
    }
    schemaMap.value = map;
  } catch (e) {
    console.warn("ConfigTree: failed to load schema for tooltips", e);
  }
});

function getTooltip(type, cls) {
  if (!type || !cls) return { desc: "", source: "", params: {} };
  return schemaMap.value[`${type}::${cls}`] || { desc: "", source: "", params: {} };
}

function esc(s) {
  // &quot; matters for attribute values (data-path/data-value) — without it,
  // a quote inside the JSON terminates the attribute early.
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
  if (c === "MathOp") {
    const l = node.left ? fmtExpr(node.left) : "0";
    const r = node.right ? fmtExpr(node.right) : "0";
    return `(${l} <span class="c-op">${esc(node.op || "+")}</span> ${r})`;
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
    const c = clsOverride || "";
    return `<span class="${c}">${esc(val.type)}</span>::<span class="${c}">${esc(val.class)}</span>`;
  }
  return esc(String(val));
}

const PRIORITY = ["name", "description", "trial_count"];

function nonMeta(obj) {
  const entries = Object.entries(obj).filter(([k]) => k !== "type" && k !== "class");
  entries.sort(([a], [b]) => {
    const ai = PRIORITY.indexOf(a), bi = PRIORITY.indexOf(b);
    if (ai >= 0 && bi >= 0) return ai - bi;
    if (ai >= 0) return -1;
    if (bi >= 0) return 1;
    return a.localeCompare(b);
  });
  return entries;
}

function prefixHtml(segments) {
  return segments.map(s =>
    s.cls ? `<span class="${s.cls}">${s.text}</span>` : s.text
  ).join("");
}

function connHtml(conn, cls) {
  return `<span class="${cls}">${conn}</span>`;
}

function _leaf(v, p) {
  const a = props.editable
    ? ` data-leaf data-path="${esc(JSON.stringify(p))}" data-value="${esc(String(v ?? ''))}"`
    : "";
  return fmtVal(v).replace(/^<span/, `<span${a}`);
}

function build(obj, preSegs, isLast, blockCls, gidx, path) {
  path = path || [];
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
          const tinfo = getTooltip(item.type, item.class);
          lines.push({
            cls: tc,
            html: `${cpre}${connHtml(jconn, blockCls)}<span class="${tc}">[${j}]</span> ${typeLabel(item, tc)}`,
            tooltip: tinfo.desc, source: tinfo.source, params: tinfo.params,
            typeName: item.type, className: item.class,
            delay: 4,
          });
          const inner = {};
          for (const [k, v] of nonMeta(item)) inner[k] = v;
          if (Object.keys(inner).length) {
            lines.push(...build(inner, jSegs, jlast, tc, gidx, [...path, key, j]));
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
      const tinfo = getTooltip(val.type, val.class);
      const keySpan = `<span class="${tc}"><b>${esc(key)}</b></span>`;
      lines.push({
        cls: tc,
        html: `${pre}${connHtml(conn, blockCls)}${keySpan} ${typeLabel(val, tc)}`,
        tooltip: tinfo.desc, source: tinfo.source, params: tinfo.params,
        typeName: val.type, className: val.class,
        delay: 8,
      });
      const inner = {};
      for (const [k, v] of nonMeta(val)) inner[k] = v;
      if (Object.keys(inner).length) {
        lines.push(...build(inner, childSegs, last, tc, gidx, [...path, key]));
      }
    } else {
      const txt = (val && typeof val === "object") ? typeLabel(val, gidx) : _leaf(val, [...path, key]);
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
  const rootTip = getTooltip(props.config.type, props.config.class);
  return [{
    cls: rootCls, html: rootHtml,
    tooltip: rootTip.desc, source: rootTip.source, params: rootTip.params,
    typeName: props.config.type, className: props.config.class,
    delay: 0,
  }, ...build(inner, [], true, rootCls, gidx, [])];
});
</script>

<template>
  <TerminalCard :title="title" :min-width="64" :collapsible="true" v-if="config">
    <div
      v-for="(line, i) in lines"
      :key="'l' + i"
      :class="['tree-line', line.cls]"
      v-html="' ' + line.html"
      @mouseenter="showTip($event, line)"
      @mousemove="moveTip"
      @mouseleave="hideTip"
    ></div>

    <!-- Floating tooltip panel -->
    <Teleport to="body">
      <div
        v-if="tip.visible"
        class="tree-tip"
        :style="{ left: tip.x + 'px', top: tip.y + 'px' }"
        @mouseenter="cancelHide"
        @mouseleave="hideTip"
      >
        <div class="tip-header">
          <span class="g">{{ tip.typeName }}</span>::<span class="g">{{ tip.className }}</span>
        </div>
        <div class="tip-desc dim" v-if="tip.tooltip">{{ tip.tooltip }}</div>
        <div class="tip-source dim" v-if="tip.source">{{ tip.source }}</div>
        <div class="tip-params" v-if="Object.keys(tip.params).length">
          <div class="g">params</div>
          <div v-for="(p, pname) in tip.params" :key="pname" class="dim">
            <span class="a">{{ pname }}</span>: {{ p.type || "?" }}
            <template v-if="p.default !== null && p.default !== undefined">
              = {{ p.default }}
            </template>
            <span class="dim"> — {{ p.description }}</span>
          </div>
        </div>
      </div>
    </Teleport>
  </TerminalCard>
  <TerminalCard :title="title" :min-width="40" :collapsible="true" v-else>
    <div class="dim"><TypedSpan text=" (no config loaded)" :speed="TYPE.fast" /></div>
  </TerminalCard>
</template>

<style scoped>
.tree-line {
  white-space: pre;
  line-height: var(--lh-body);
  font-size: var(--fs-base);
  cursor: default;
  overflow: hidden; text-overflow: ellipsis;
}
.tree-line:hover {
  background: rgba(79,232,124,0.04);
}
</style>

<style>
/* Not scoped — teleported to body */
.tree-tip {
  position: fixed;
  z-index: 200;
  max-width: 52ch;
  background: var(--surface-2);
  border: var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: var(--sp-sm) var(--sp-md);
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  line-height: var(--lh-body);
  box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 8px rgba(79,232,124,0.08);
  pointer-events: auto;
}
.tip-header {
  font-size: var(--fs-base);
  margin-bottom: var(--sp-xxs);
}
.tip-desc {
  margin-bottom: var(--sp-xxs);
}
.tip-source {
  font-size: var(--fs-xs);
  margin-bottom: var(--sp-xs);
}
.tip-params {
  margin-top: var(--sp-xxs);
}
.tip-params .g {
  margin-bottom: var(--sp-xxs);
}
</style>
