<script setup>
import { ref, onUnmounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";
import AsciiTable from "./AsciiTable.vue";
import CopyButton from "./CopyButton.vue";
import ServerPopup from "./ServerPopup.vue";

const { servers } = useFirestore();

const now = ref(Date.now());
const tick = setInterval(() => { now.value = Date.now(); }, 1000);
onUnmounted(() => clearInterval(tick));

const selectedServer = ref(null);

const COLUMNS = [
  { key: "name", header: "NAME" },
  { key: "status", header: "STATUS" },
  { key: "version", header: "VER" },
  { key: "current_job", header: "JOB" },
  { key: "cpu", header: "CPU%", align: "right" },
  { key: "mem", header: "MEM%", align: "right" },
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
  if (key === "version") return { text: row.version || "-" };
  if (key === "current_job") {
    const ids = row.active_job_ids || [];
    if (!ids.length) return { text: "-" };
    return { text: String(ids.length), cls: "a" };
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
  if (!row.last_seen) return "never".padEnd(8);
  const last = row.last_seen.toDate ? row.last_seen.toDate().getTime() : Date.parse(row.last_seen);
  if (isNaN(last)) return "?".padEnd(8);
  const sec = Math.round((now.value - last) / 1000);
  let out;
  if (sec < 60) out = `${sec}s ago`;
  else if (sec < 3600) out = `${Math.round(sec / 60)}m ago`;
  else out = `${Math.round(sec / 3600)}h ago`;
  // Fixed width so ticking ages never change column/box width
  return out.padEnd(8);
}
</script>

<template>
  <div class="server-list">
    <AsciiTable
      title="servers"
      :columns="COLUMNS"
      :rows="servers"
      :formatCell="formatCell"
      :minWidth="88"
      emptyText="(no servers connected)"
      :clickableRows="true"
      noType
      @rowClick="(row) => (selectedServer = row)"
    />

    <ServerPopup :server="selectedServer" @close="selectedServer = null" />

    <!-- Setup instructions -->
    <TerminalCard title="server setup" :min-width="40" :collapsible="true" :startCollapsed="true">
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
    </TerminalCard>
  </div>
</template>

<style scoped>
.server-list { display: flex; flex-direction: column; }
.setup-pre {
  color: var(--text); white-space: pre-wrap;
  padding: var(--sp-xxs) 0;
  font-size: var(--fs-md);
}
a { text-decoration: none; }
a:hover { text-decoration: underline; }
</style>
