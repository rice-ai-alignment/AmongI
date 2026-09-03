<script setup>
import { ref, computed, onMounted } from "vue";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";
import StaggerBlock from "./StaggerBlock.vue";
import ConfigCard from "./ConfigCard.vue";
import { TYPE } from "../composables/typeSettings.js";

const schema = ref(null);
const examples = ref([]);
const selectedExample = ref(null);
const exampleJson = ref("");
const schemaLoading = ref(true);
const selectedType = ref(null);
const expanded = ref({});

onMounted(async () => {
  try {
    const [schemaRes, basicRes, smallRes, timerRes] = await Promise.all([
      fetch("/schema.json"),
      fetch("/sample_data/among_us/example_basic.json"),
      fetch("/sample_data/among_us/example_small_kill.json"),
      fetch("/sample_data/among_us/example_timer.json"),
    ]);
    schema.value = await schemaRes.json();

    const parseExample = async (res, filename) => {
      const raw = await res.text();
      const data = JSON.parse(raw);
      return { filename, name: data.name || data.id, description: data.description || "", json: raw, data };
    };
    examples.value = [
      await parseExample(basicRes, "example_basic.json"),
      await parseExample(smallRes, "example_small_kill.json"),
      await parseExample(timerRes, "example_timer.json"),
    ];
    // Auto-expand top-level groups
    for (const r of treeLines.value) {
      if (r.folder && r.depth === 0) expanded.value[r.key] = true;
    }
    schemaLoading.value = false;
  } catch (e) {
    console.error("Failed to load schema/examples:", e);
    schemaLoading.value = false;
  }
});

function selectExample(ex) {
  selectedExample.value = ex;
  exampleJson.value = ex.json;
  selectedType.value = null;
}
function selectType(typeName) {
  selectedType.value = typeName;
  selectedExample.value = null;
}
function toggleExpand(key) {
  expanded.value[key] = !expanded.value[key];
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ── Group types by functional area from source path ──────────────────

const CATEGORY_MAP = {
  "actions.py": "agent",
  "agents.py": "agent",
  "context_manager.py": "agent",
  "engine.py": "engine",
  "maps.py": "world",
  "map_visualizer.py": "world",
  "position.py": "world",
  "conditions.py": "logic",
  "expressions.py": "logic",
  "refs.py": "logic",
  "win_conditions.py": "logic",
  "phases.py": "phase",
};

const CATEGORY_LABELS = {
  agent: "agent",
  engine: "engine",
  world: "world",
  logic: "logic",
  phase: "phase",
};

function catForSource(source) {
  if (!source) return null;
  const file = source.split("/").pop();
  return CATEGORY_MAP[file] || null;
}

function gameForSource(source) {
  if (!source || !source.startsWith("games/")) return null;
  const parts = source.split("/");
  return parts.length >= 2 ? parts[1].replace(/_/g, " ") : null;
}

// ── Flat tree lines with ASCII connectors ───────────────────────────

const treeLines = computed(() => {
  if (!schema.value) return [];
  const lines = [];

  function pushTree(items, depth, pre) {
    for (let i = 0; i < items.length; i++) {
      const last = i === items.length - 1;
      const conn = last ? "└── " : "├── ";
      const chPre = pre + (last ? "    " : "│   ");
      const item = items[i];
      lines.push({
        key: item.key,
        depth,
        prefix: pre + conn,
        label: item.label,
        count: item.count,
        folder: !!item.children,
        typeName: item.typeName || null,
        expanded: !!expanded.value[item.key],
      });
      if (item.children && expanded.value[item.key]) {
        pushTree(item.children, depth + 1, chPre);
      }
    }
  }

  // Group types by category (agent/engine/world/logic) or game name
  const cats = {};  // {catKey: {label, types: {tname: info}}}
  const games = {}; // {gameName: {label, types: {}}}

  for (const [tname, tinfo] of Object.entries(schema.value)) {
    const classes = tinfo.classes || {};
    const sources = Object.values(classes).map(c => c.source || "").filter(Boolean);
    const src = sources[0] || "";
    const game = gameForSource(src);

    if (game) {
      if (!games[game]) games[game] = { key: game, label: game, types: {} };
      games[game].types[tname] = tinfo;
    } else {
      const cat = catForSource(src) || "other";
      if (!cats[cat]) cats[cat] = { key: cat, label: CATEGORY_LABELS[cat] || cat, types: {} };
      cats[cat].types[tname] = tinfo;
    }
  }

  // Build root-level items: category folders + game folder
  const roots = [];
  const catOrder = ["agent", "engine", "world", "logic", "phase"];
  for (const ck of catOrder) {
    if (!cats[ck]) continue;
    const types = Object.entries(cats[ck].types).sort(([a], [b]) => a.localeCompare(b));
    roots.push({
      key: ck, label: cats[ck].label,
      count: types.length,
      children: types.map(([tname, tinfo]) => ({
        key: tname, label: tname, typeName: tname,
        count: Object.keys(tinfo.classes || {}).length,
      })),
    });
  }

  // Game folder with nested games
  if (Object.keys(games).length) {
    const gameChildren = Object.entries(games).sort(([a], [b]) => a.localeCompare(b)).map(([gk, gg]) => {
      const types = Object.entries(gg.types).sort(([a], [b]) => a.localeCompare(b));
      return {
        key: gk, label: gg.label,
        count: types.length,
        children: types.map(([tname, tinfo]) => ({
          key: tname, label: tname, typeName: tname,
          count: Object.keys(tinfo.classes || {}).length,
        })),
      };
    });
    roots.push({
      key: "games", label: "game",
      count: Object.keys(games).length,
      children: gameChildren,
    });
  }

  pushTree(roots, 0, "");
  return lines;
});

// ── Selected type detail ────────────────────────────────────────────

const selectedTypeInfo = computed(() => {
  if (!selectedType.value || !schema.value) return null;
  return schema.value[selectedType.value];
});

// ── Formatters ──────────────────────────────────────────────────────

function fmtDefault(d) {
  if (d === null || d === undefined) return "—";
  const s = String(d);
  if (s.startsWith("'") && s.endsWith("'")) return s.slice(1, -1);
  return s;
}
function fmtType(t) {
  if (t === "component" || t === "NoneType") return "component";
  return t;
}

function buildClassLines(cinfo) {
  const lines = [];
  if (cinfo.description && cinfo.description !== cinfo._key) {
    lines.push({ delay: 0, html: `<span class="dim">${esc(cinfo.description)}</span>` });
  }
  if (Object.keys(cinfo.params).length) {
    lines.push({ delay: 40, html: '<span class="g">params</span>' });
    for (const [pname, p] of Object.entries(cinfo.params)) {
      let h = `  <span class="g">${esc(pname)}</span>`;
      h += `<span class="a">: ${esc(fmtType(p.type))}</span>`;
      if (p.default !== null && p.default !== undefined) {
        h += `<span class="dim"> = ${esc(fmtDefault(p.default))}</span>`;
      }
      h += `<span class="dim"> — ${esc(p.description)}</span>`;
      lines.push({ delay: 20, html: h });
    }
  }
  if (cinfo.exposes) {
    lines.push({ delay: 40, html: '<span class="g">exposes</span>' });
    const vars = cinfo.exposes.variables;
    if (vars && Object.keys(vars).length) {
      lines.push({ delay: 20, html: '  <span class="a">variables</span>' });
      for (const [vname, desc] of Object.entries(vars)) {
        const ds = typeof desc === "string" ? desc : (desc.desc || desc.type || "");
        const parts = ds.split(" — ");
        lines.push({ delay: 10,
          html: `    <span>${esc(vname)}</span><span class="a">: ${esc(parts[0]||"")}</span><span class="dim"> — ${esc(parts.slice(1).join(" — ")||ds)}</span>` });
      }
    }
    const funcs = cinfo.exposes.functions;
    if (funcs && Object.keys(funcs).length) {
      lines.push({ delay: 20, html: '  <span class="a">functions</span>' });
      for (const [fname, desc] of Object.entries(funcs)) {
        const args = (desc.args || []).join(", ");
        lines.push({ delay: 10,
          html: `    <span>${esc(fname)}(</span><span class="a">${esc(args)}</span><span>)</span> → <span class="g">${esc(desc.returns||"any")}</span><span class="dim"> — ${esc(desc.desc||"")}</span>` });
      }
    }
  }
  if (!Object.keys(cinfo.params).length && !cinfo.exposes) {
    lines.push({ delay: 0, html: '<span class="dim">(no params or exposures)</span>' });
  }
  return lines;
}

function handleLineClick(line) {
  if (line.folder) {
    toggleExpand(line.key);
  } else if (line.typeName) {
    selectType(line.typeName);
  }
}
</script>

<template>
  <div class="config-viewer">
    <!-- Sidebar -->
    <div class="cv-sidebar">
      <TerminalCard title="components" :min-width="30" :collapsible="false">
        <div v-if="schemaLoading" class="cv-tree">
          <div class="cv-line dim"> loading...</div>
        </div>
        <div v-else class="cv-tree">
          <div
            v-for="(line, i) in treeLines"
            :key="line.key + '@' + line.depth"
            class="cv-line"
            :class="{
              'cv-folder': line.folder,
              active: selectedType === line.typeName,
              'dim': !line.folder && !line.typeName,
            }"
            @click="handleLineClick(line)"
          >
            <span class="cv-prefix">{{ line.prefix }}</span>
            <span v-if="line.folder" class="cv-label">{{ line.expanded ? '▾' : '▸' }} {{ line.label }}</span>
            <span v-else class="cv-label">{{ line.label }}</span>
            <span class="dim cv-count">{{ line.count }}</span>
          </div>
        </div>
      </TerminalCard>

      <TerminalCard title="examples" :min-width="30" :collapsible="false" style="margin-top:var(--sp-md)">
        <div class="cv-example-list">
          <div
            v-for="ex in examples"
            :key="ex.filename"
            class="cv-line cv-click"
            :class="{ active: selectedExample === ex }"
            @click="selectExample(ex)"
          >
            <span class="cv-label">{{ ex.name }}</span>
          </div>
        </div>
      </TerminalCard>
    </div>

    <!-- Main content -->
    <div class="cv-main">
      <div v-if="selectedTypeInfo" :key="'type-' + selectedType">
        <StaggerBlock>
          <div v-for="(cinfo, cname) in selectedTypeInfo.classes" :key="cname">
            <TerminalCard :title="selectedType + ' :: ' + cname" :min-width="50" :collapsible="true">
              <div v-if="cinfo.source" class="cv-source dim">
                <TypedSpan :text="' ' + esc(cinfo.source)" :speed="TYPE.fast" />
              </div>
              <div v-for="line in buildClassLines({ ...cinfo, _key: cname })" :key="line.delay + '-' + line.html.slice(0,20)">
                <TypedSpan :text="' ' + line.html" :speed="TYPE.fast" :delay="line.delay" />
              </div>
            </TerminalCard>
          </div>
        </StaggerBlock>
      </div>

      <div v-else-if="selectedExample" :key="'ex-' + selectedExample.filename">
        <TerminalCard :title="selectedExample.name" :min-width="50" :collapsible="false">
          <div class="cv-example-meta"><span class="dim">{{ selectedExample.description }}</span></div>
          <div class="cv-example-meta"><span class="dim">file: {{ selectedExample.filename }}</span></div>
        </TerminalCard>
        <ConfigCard :config="selectedExample.data" :title="selectedExample.filename" />
      </div>

      <div v-else class="cv-empty">
        <div class="box-label">┌─ component database ─┐</div>
        <div class="dim" style="margin-top:8px"> select a component type to view its classes and parameters</div>
        <div class="dim"> or select an example to see a full config</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.config-viewer {
  display: flex; gap: 10px; flex: 1; overflow: hidden; min-height: 0;
}
.cv-sidebar {
  width: 32ch; flex-shrink: 0; overflow-y: auto;
}
.cv-sidebar::-webkit-scrollbar       { width: var(--scrollbar-w); }
.cv-sidebar::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }
.cv-main {
  flex: 1; overflow-y: auto; min-width: 0;
}
.cv-main::-webkit-scrollbar       { width: var(--scrollbar-w); }
.cv-main::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }

.cv-tree { display: flex; flex-direction: column; }
.cv-line {
  white-space: pre; line-height: var(--lh-body);
  font-size: var(--fs-base); cursor: default;
  display: flex; align-items: baseline;
}
.cv-line.cv-click, .cv-line.cv-folder, .cv-line.active { cursor: pointer; }
.cv-line:hover { color: var(--text); }
.cv-line.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }

.cv-prefix { color: var(--text-dim); flex-shrink: 0; }
.cv-label { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.cv-count { font-size: var(--fs-sm); flex-shrink: 0; margin-left: var(--sp-xxs); }

.cv-example-list { display: flex; flex-direction: column; }
.cv-example-list .cv-line { cursor: pointer; color: var(--text-dim); }
.cv-example-list .cv-line:hover { color: var(--text); }
.cv-example-list .cv-line.active { color: var(--green); }

.cv-json {
  font-size: var(--fs-base); line-height: 1.4; white-space: pre; overflow-x: auto;
  color: var(--text-dim); max-height: 70vh; overflow-y: auto;
}
.cv-json::-webkit-scrollbar       { width: var(--scrollbar-w); height: var(--scrollbar-w); }
.cv-json::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }
.cv-json code { font-family: var(--font-mono); }

.cv-empty { padding-top: var(--sp-xs); white-space: pre; }
.cv-source { font-size: var(--fs-sm); padding-bottom: var(--sp-xxs); }
.cv-example-meta { font-size: var(--fs-sm); }
.box-label { font-size: var(--fs-ui); color: var(--green); text-shadow: var(--glow-medium); }
</style>
