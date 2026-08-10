<script setup>
import { ref } from "vue";
import TerminalCard from "./TerminalCard.vue";
import ConfigViewer from "./ConfigViewer.vue";

const section = ref("workflow");

const sections = [
  { key: "workflow", label: "workflow" },
  { key: "components", label: "component database" },
  { key: "jobs", label: "job system" },
  { key: "server", label: "server setup" },
];
</script>

<template>
  <div class="docs">
    <!-- Top tabs -->
    <div class="docs-tabs">
      <span
        v-for="s in sections" :key="s.key"
        class="tab"
        :class="{ active: section === s.key }"
        @click="section = s.key"
      >[ {{ s.label }} ]</span>
    </div>

    <!-- Content -->
    <div class="docs-main">
      <!-- Workflow -->
      <div v-if="section === 'workflow'">
        <TerminalCard title="workflow" :min-width="60" :collapsible="false">
          <div class="docs-body">
            <div class="g">▸ overview</div>
            <div class="dim">
              Among-I is a multi-agent LLM simulation engine. You design
              experiments (game configs), queue them as jobs, and servers
              pick them up and run them. Results stream back to the
              dashboard in real time.
            </div>

            <div class="g">▸ 1. create a study</div>
            <div class="dim">
              A <b>study</b> groups related experiments. Click the
              <span class="g">[ + new study ]</span> card on the experiments
              tab, or use <span class="a">create study &lt;name&gt;</span> in
              the command line. Each study has a name and description.
            </div>

            <div class="g">▸ 2. create an experiment</div>
            <div class="dim">
              Select a study, then click
              <span class="g">[ + new experiment ]</span> in the sidebar.
              Choose a <b>template</b> from the dropdown to pre-fill the
              config, or start blank and build your own. The config is
              stored on the experiment document in Firestore.
            </div>

            <div class="g">▸ 3. configure the experiment</div>
            <div class="dim">
              Select the experiment and click the
              <span class="g">[ config ]</span> tab. Use the
              <span class="g">[ tree ]</span> view to explore the config,
              <span class="g">[ json ]</span> to see the raw JSON, and
              <span class="g">[ edit ]</span> to modify it. Click
              <span class="g">[ save to experiment ]</span> to persist
              changes. Use <span class="g">[ validate ]</span> to check
              your config against the schema.
            </div>

            <div class="g">▸ 4. run the experiment</div>
            <div class="dim">
              Switch to the <span class="g">[ jobs ]</span> tab. Set the
              number of games and click
              <span class="g">[ run on server ]</span>. The dashboard saves
              your config to Firestore and queues a job. Any available
              server will claim and execute it. You can also use the
              <span class="g">[ copy command ]</span> button to get a
              <span class="a">python run.py</span> command for local
              execution.
            </div>

            <div class="g">▸ 5. monitor progress</div>
            <div class="dim">
              The <span class="g">[ jobs ]</span> tab shows active jobs
              with status, elapsed time, and server assignment. Completed
              and failed jobs appear in the history section. Results
              (game count, kills, win distribution) update as each game
              finishes.
            </div>

            <div class="g">▸ 6. view results</div>
            <div class="dim">
              Once a job completes, switch back to
              <span class="g">[ stats ]</span> to see aggregate stats,
              win charts, player tables, and match logs. Data streams
              from the engine through the bridge to Firestore in real
              time — no polling needed.
            </div>
          </div>
        </TerminalCard>
      </div>

      <!-- Component database -->
      <div v-if="section === 'components'">
        <ConfigViewer />
      </div>

      <!-- Job system -->
      <div v-if="section === 'jobs'">
        <TerminalCard title="job system" :min-width="60" :collapsible="false">
          <div class="docs-body">
            <div class="g">▸ lifecycle</div>
            <div class="dim">
              <span class="a">queued</span> → dashboard creates the job
              doc<br />
              <span class="g">claimed</span> → server picks it up<br />
              <span class="g">running</span> → engine is executing<br />
              <span class="">completed</span> → all games finished<br />
              <span class="r">failed</span> → error occurred
            </div>

            <div class="g">▸ job document</div>
            <div class="dim">
              Jobs live in the <span class="a">jobs</span> Firestore
              collection. Each job has: study_id, experiment_code,
              max_games, created_by, status, claimed_by, timestamps
              (created/claimed/started/finished), result (summary), and
              error (if failed).<br />
              <b>Config is NOT stored on the job</b> — the server reads
              it from the experiment document at runtime. This ensures
              the config can be edited and re-run without updating the
              job.
            </div>

            <div class="g">▸ server dispatch</div>
            <div class="dim">
              Servers poll <span class="a">jobs where status == "queued"</span>
              ordered by created_at (oldest first). The first server to
              poll claims the job in a Firestore transaction. Servers can
              filter by study with <span class="a">--study</span>.
            </div>

            <div class="g">▸ permissions</div>
            <div class="dim">
              Users need <span class="a">can_run_experiments: true</span>
              on their <span class="a">users/{uid}</span> document. This
              can only be set via Admin SDK. Jobs created by unauthorized
              users are marked failed with "permission denied."
            </div>

            <div class="g">▸ manual execution</div>
            <div class="dim">
              Copy the command from the jobs tab and run locally:<br />
              <span class="a">python run.py --config-firestore --firebase
              --study S --experiment E</span><br />
              This reads the config from Firestore, runs the engine
              locally, and pushes results back.
            </div>
          </div>
        </TerminalCard>
      </div>

      <!-- Server setup -->
      <div v-if="section === 'server'">
        <TerminalCard title="server setup" :min-width="60" :collapsible="false">
          <div class="docs-body">
            <div class="g">▸ prerequisites</div>
            <div class="dim">
              1. <b>firebase-key.json</b> — service account key from
              Firebase Console → Project Settings → Service Accounts.<br />
              2. <b>.env</b> file with OPEN_ROUTER_API_KEY (or
              OPENAI_API_KEY) and MODEL.<br />
              3. Python 3.12+ with dependencies from requirements.txt.
            </div>

            <div class="g">▸ docker</div>
            <div class="dim">
              <span class="a">docker compose up -d</span><br />
              Uses docker-compose.yml. Place firebase-key.json in the
              engine/ directory. The container auto-registers and starts
              processing jobs.
            </div>

            <div class="g">▸ bare metal</div>
            <div class="dim">
              <span class="a">cd engine && python server_handler.py
              --name my-server</span><br />
              Flags: <span class="a">--study ID</span> (filter jobs),
              <span class="a">--render</span> (Godot relay),
              <span class="a">--heartbeat-interval 30</span>,
              <span class="a">--poll-interval 5</span>,
              <span class="a">--log-dir ../log</span>.
            </div>

            <div class="g">▸ server document</div>
            <div class="dim">
              Servers register in the <span class="a">servers</span>
              collection with: name, hostname, status (online/busy/offline),
              last_seen, cpu/mem/gpu utilization, current_job_id,
              jobs_completed count, render_active, and funnel_url.
              Heartbeats update every N seconds.
            </div>

            <div class="g">▸ stale job recovery</div>
            <div class="dim">
              On startup, servers fail any jobs they previously claimed
              that are still in claimed/running state (server crash
              recovery). Jobs claimed by other servers are not touched
              unless they exceed a 30-minute timeout.
            </div>
          </div>
        </TerminalCard>
      </div>
    </div>
  </div>
</template>

<style scoped>
.docs {
  flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0;
}
.docs-tabs {
  display: flex; gap: var(--sp-xl);
  padding: var(--sp-xxs) 0 var(--sp-xs);
  margin-bottom: var(--sp-xs);
  border-bottom: var(--border-hair); flex-shrink: 0;
}
.docs-tabs .tab {
  font-size: var(--fs-sm); color: var(--text-dim); cursor: pointer;
  white-space: nowrap;
}
.docs-tabs .tab:hover  { color: var(--text); }
.docs-tabs .tab.active { color: var(--green); text-shadow: 0 0 5px rgba(79,232,124,0.3); }

.docs-main { flex: 1; overflow-y: auto; min-width: 0; }
.docs-main::-webkit-scrollbar { width: var(--scrollbar-w); }
.docs-main::-webkit-scrollbar-thumb { background: var(--border); border-radius: var(--radius-sm); }

.docs-body {
  font-size: var(--fs-base); line-height: var(--lh-loose);
  white-space: normal; word-wrap: break-word; overflow-wrap: break-word;
}
.docs-body .g { margin-top: var(--sp-sm); }
.docs-body .dim { margin-bottom: var(--sp-xxs); padding-left: var(--sp-sm); }
.docs-body .dim + .g { margin-top: var(--sp-lg); }
</style>
