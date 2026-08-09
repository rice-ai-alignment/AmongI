<script setup>
import { ref, computed, onMounted } from "vue";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";
import StaggerBlock from "./StaggerBlock.vue";
import { TYPE } from "../composables/typeSettings.js";

const schema = ref(null);
const examples = ref([]);
const selectedExample = ref(null);
const exampleJson = ref("");
const schemaLoading = ref(true);
const selectedType = ref(null);

onMounted(async () => {
  try {
    const [schemaRes, basicRes, smallRes, timerRes] = await Promise.all([
      fetch("/schema.json"),
      fetch("/sample_data/example_basic.json"),
      fetch("/sample_data/example_small_kill.json"),
      fetch("/sample_data/example_timer.json"),
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

const typeNames = computed(() => {
  if (!schema.value) return [];
  return Object.keys(schema.value).sort();
});

const selectedTypeInfo = computed(() => {
  if (!selectedType.value || !schema.value) return null;
  return schema.value[selectedType.value];
});

// ── format helpers ─────────────────────────────────────────────────
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

// Build pre-formatted HTML lines for a class's params and exposures
function buildClassLines(cinfo) {
  const lines = [];

  // Description
  if (cinfo.description && cinfo.description !== cinfo._key) {
    lines.push({ delay: 0, html: `<span class="dim">${esc(cinfo.description)}</span>` });
  }

  // Params
  if (Object.keys(cinfo.params).length) {
    lines.push({ delay: 40, html: '<span class="g">params</span>' });
    for (const [pname, p] of Object.entries(cinfo.params)) {
      let html = `  <span class="g">${esc(pname)}</span>`;
      html += `<span class="a">: ${esc(fmtType(p.type))}</span>`;
      if (p.default !== null && p.default !== undefined) {
        html += `<span class="dim"> = ${esc(fmtDefault(p.default))}</span>`;
      }
      html += `<span class="dim"> — ${esc(p.description)}</span>`;
      lines.push({ delay: 20, html });
    }
  }

  // Exposures
  if (cinfo.exposes) {
    lines.push({ delay: 40, html: '<span class="g">exposes</span>' });
    const vars = cinfo.exposes.variables;
    if (vars && Object.keys(vars).length) {
      lines.push({ delay: 20, html: '  <span class="a">variables</span>' });
      for (const [vname, desc] of Object.entries(vars)) {
        const ds = typeof desc === "string" ? desc : (desc.desc || desc.type || "");
        const parts = ds.split(" — ");
        const typeStr = parts[0] || "";
        const descStr = parts.slice(1).join(" — ") || ds;
        lines.push({
          delay: 10,
          html: `    <span>${esc(vname)}</span><span class="a">: ${esc(typeStr)}</span><span class="dim"> — ${esc(descStr)}</span>`,
        });
      }
    }
    const funcs = cinfo.exposes.functions;
    if (funcs && Object.keys(funcs).length) {
      lines.push({ delay: 20, html: '  <span class="a">functions</span>' });
      for (const [fname, desc] of Object.entries(funcs)) {
        const args = (desc.args || []).join(", ");
        const returns = desc.returns || "any";
        const ds = desc.desc || "";
        lines.push({
          delay: 10,
          html: `    <span>${esc(fname)}(</span><span class="a">${esc(args)}</span><span>)</span> → <span class="g">${esc(returns)}</span><span class="dim"> — ${esc(ds)}</span>`,
        });
      }
    }
  }

  if (!Object.keys(cinfo.params).length && !cinfo.exposes) {
    lines.push({ delay: 0, html: '<span class="dim">(no params or exposures)</span>' });
  }

  return lines;
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
</script>

<template>
  <div class="config-viewer">
    <!-- Sidebar -->
    <div class="cv-sidebar">
      <TerminalCard title="components" :min-width="26" :collapsible="false">
        <div v-if="schemaLoading" class="cv-type-list">
          <div class="cv-type-item dim"><TypedSpan text="loading..." :speed="TYPE.fast" /></div>
        </div>
        <div v-else class="cv-type-list">
          <div
            v-for="tname in typeNames"
            :key="tname"
            class="cv-type-item"
            :class="{ active: selectedType === tname }"
            @click="selectType(tname)"
          >
            <TypedSpan :text="tname" :speed="TYPE.fast" />
            <span class="dim cv-count">{{ Object.keys(schema[tname].classes || {}).length }}</span>
          </div>
        </div>
      </TerminalCard>

      <TerminalCard title="examples" :min-width="26" :collapsible="false" style="margin-top:var(--sp-md)">
        <div class="cv-type-list">
          <div
            v-for="ex in examples"
            :key="ex.filename"
            class="cv-type-item"
            :class="{ active: selectedExample === ex }"
            @click="selectExample(ex)"
          >
            <TypedSpan :text="ex.name" :speed="TYPE.fast" />
          </div>
        </div>
      </TerminalCard>
    </div>

    <!-- Main content -->
    <div class="cv-main">
      <!-- Schema viewer -->
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

      <!-- Example JSON viewer -->
      <div v-else-if="selectedExample" :key="'ex-' + selectedExample.filename">
        <TerminalCard :title="selectedExample.name" :min-width="50" :collapsible="false">
          <div><TypedSpan :text="' <span class=&quot;dim&quot;>' + esc(selectedExample.description) + '</span>'" :speed="TYPE.fast" /></div>
          <div><TypedSpan :text="' <span class=&quot;dim&quot;>file: ' + esc(selectedExample.filename) + '</span>'" :speed="TYPE.fast" :delay="100" /></div>
        </TerminalCard>
        <TerminalCard title="raw config" :min-width="50" :collapsible="true" style="margin-top:var(--sp-xs)">
          <pre class="cv-json"><code>{{ exampleJson }}</code></pre>
        </TerminalCard>
      </div>

      <!-- Empty state -->
      <div v-else class="cv-empty">
        <div class="box-label">┌─ component database ─┐</div>
        <div class="dim" style="margin-top:8px"><TypedSpan text="select a component type to view its classes and parameters" :speed="TYPE.normal" /></div>
        <div class="dim"><TypedSpan text="or select an example to see a full config" :speed="TYPE.normal" :delay="80" /></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.config-viewer {
  display: flex; gap: 10px; flex: 1; overflow: hidden; min-height: 0;
}
.cv-sidebar {
  width: 28ch; flex-shrink: 0; overflow-y: auto;
}
.cv-sidebar::-webkit-scrollbar       { width: var(--scrollbar-w); }
.cv-sidebar::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }
.cv-main {
  flex: 1; overflow-y: auto; min-width: 0;
}
.cv-main::-webkit-scrollbar       { width: var(--scrollbar-w); }
.cv-main::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }

.cv-type-list { display: flex; flex-direction: column; }
.cv-type-item {
  cursor: pointer; padding: 1px 0; color: var(--text-dim);
  font-size: var(--fs-ui); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: all 0.12s ease; display: flex; justify-content: space-between; align-items: center;
}
.cv-type-item:hover { color: var(--text); padding-left: var(--sp-xxs); }
.cv-type-item.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }
.cv-count { font-size: var(--fs-md); }

.cv-json {
  font-size: var(--fs-base); line-height: 1.4; white-space: pre; overflow-x: auto;
  color: var(--text-dim); max-height: 70vh; overflow-y: auto;
}
.cv-json::-webkit-scrollbar       { width: var(--scrollbar-w); height: var(--scrollbar-w); }
.cv-json::-webkit-scrollbar-thumb  { background: var(--border); border-radius: var(--radius-sm); }
.cv-json code { font-family: var(--font-mono); }

.cv-empty { padding-top: var(--sp-xs); }
.cv-source { font-size: var(--fs-sm); padding-bottom: var(--sp-xxs); }
.box-label { font-size: var(--fs-ui); color: var(--green); text-shadow: var(--glow-medium); }
</style>
