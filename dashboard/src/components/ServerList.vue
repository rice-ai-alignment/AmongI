<script setup>
import { ref, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";
import AsciiTable from "./AsciiTable.vue";
import CopyButton from "./CopyButton.vue";

const { servers } = useFirestore();

const now = ref(Date.now());
const tick = setInterval(() => { now.value = Date.now(); }, 1000);
onUnmounted(() => clearInterval(tick));

const showSetup = ref(false);

const COLUMNS = [
  { key: "name", header: "NAME" },
  { key: "status", header: "STATUS" },
  { key: "current_job", header: "JOB" },
  { key: "cpu", header: "CPU%", align: "right" },
  { key: "mem", header: "MEM%", align: "right" },
  { key: "gpu", header: "GPU%", align: "right" },
  { key: "jobs", header: "DONE", align: "right" },
  { key: "seen", header: "SEEN" },
];

const dockerCmd = `docker run -d --name amongi-server \\
  -v $(pwd)/firebase-key.json:/app/engine/firebase-key.json:ro \\
  -v amongi-logs:/app/log \\
  -p 8081:8081 \\
  amongi-server --render`;

const composeYml = `# 1. Place firebase-key.json in engine/
# 2. Run: docker compose up -d`;

function formatCell(key, val, row) {
  if (key === "name") return { text: row.name || row.id || "?", bold: true };
  if (key === "status") return _statusCell(row);
  if (key === "current_job") {
    const jid = row.current_job_id;
    if (!jid) return { text: "-" };
    return { text: jid.length > 12 ? jid.slice(0, 12) + "..." : jid, cls: "a" };
  }
  if (key === "cpu") return { text: row.cpu_percent != null ? String(Math.round(row.cpu_percent)) : "-" };
  if (key === "mem") return { text: row.memory_percent != null ? String(Math.round(row.memory_percent)) : "-" };
  if (key === "gpu") return { text: row.gpu_percent != null ? String(Math.round(row.gpu_percent)) : "-" };
  if (key === "jobs") return { text: String(row.jobs_completed || 0) };
  if (key === "seen") return { text: _ageText(row) };
  return { text: String(val ?? "-") };
}

function _statusCell(row) {
  const offline = _isOffline(row);
  if (offline) return { text: "offline", cls: "r" };
  if (row.status === "busy") return { text: "busy", cls: "a" };
  return { text: "online", cls: "g" };
}

function _isOffline(row) {
  if (!row.last_seen) return true;
  const interval = (row.heartbeat_interval_sec || 30) * 1000;
  const last = row.last_seen.toDate ? row.last_seen.toDate().getTime() : Date.parse(row.last_seen);
  if (isNaN(last)) return false;
  return (now.value - last) > (interval * 2 + 15000);
}

function _ageText(row) {
  if (!row.last_seen) return "never";
  const last = row.last_seen.toDate ? row.last_seen.toDate().getTime() : Date.parse(row.last_seen);
  if (isNaN(last)) return "?";
  const sec = Math.round((now.value - last) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  return `${Math.round(sec / 3600)}h ago`;
}
</script>

<template>
  <TerminalCard title="servers" :min-width="88">
    <AsciiTable
      v-if="servers.length"
      :columns="COLUMNS"
      :rows="servers"
      :formatCell="formatCell"
      no-type
    />
    <div v-else class="dim">(no servers connected)</div>

    <!-- Setup instructions -->
    <div class="setup-bar">
      <span class="tab" :class="{ active: showSetup }" @click="showSetup = !showSetup">
        {{ showSetup ? "[ - ]" : "[ + ]" }} setup instructions
      </span>
    </div>
    <div v-if="showSetup" class="setup-body">
      <div class="dim">Servers auto-register on first heartbeat. To add one:</div>
      <br />

      <div class="g">▸ docker compose</div>
      <div class="setup-pre">$ cd AmongI &amp;&amp; docker compose up -d</div>
      <br />

      <div class="g">▸ docker run</div>
      <div class="setup-pre">$ {{ dockerCmd }}</div>
      <br />

      <div class="g">▸ prerequisites</div>
      <div class="dim">
        1. Install <a class="g" href="https://docs.docker.com/get-docker/" target="_blank">Docker</a>
        &nbsp;&nbsp;2. Place <span class="a">firebase-key.json</span> in <span class="a">engine/</span>
        <br />
        &nbsp;&nbsp;&nbsp;(Firebase Console → Project Settings → Service Accounts → Generate Key)
        <br />
        &nbsp;&nbsp;3. Build the image: <span class="a">docker compose build</span>
      </div>
      <br />

      <div class="g">▸ flags (pass after image name)</div>
      <div class="dim">
        <span class="a">--name NAME</span>&nbsp;&nbsp;&nbsp;&nbsp;server display name (default: hostname)
        <br />
        <span class="a">--render</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;start render relay for remote Godot
        <br />
        <span class="a">--funnel</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;enable Tailscale funnel (requires Tailscale)
        <br />
        <span class="a">--study ID</span>&nbsp;&nbsp;&nbsp;&nbsp;only accept jobs for this study
        <br />
        <span class="a">--log-dir DIR</span>&nbsp;log output directory (default: /app/log)
      </div>

      <br />
      <CopyButton :command="dockerCmd" label="copy docker command" />
    </div>
  </TerminalCard>
</template>

<style scoped>
.setup-bar {
  padding: var(--sp-xs) 0 0 0;
  border-top: var(--border-panel);
  margin-top: var(--sp-xs);
}
.setup-body {
  font-size: var(--fs-base);
  padding: var(--sp-xs) 0 var(--sp-xs) calc(var(--sp-sm) + 1ch);
  line-height: 1.5;
}
.setup-pre {
  color: var(--text); white-space: pre-wrap;
  padding: var(--sp-xxs) 0;
  font-size: var(--fs-md);
}
.setup-body a { text-decoration: none; }
.setup-body a:hover { text-decoration: underline; }
</style>
