import { ref, computed } from "vue";

const COLLECTION = "studies";

// ── Init ───────────────────────────────────────────────────────────
function ensureFirebase() {
  if (typeof firebase === "undefined") return false;
  if (!firebase.apps.length) {
    if (typeof FIREBASE_CONFIG !== "undefined") {
      firebase.initializeApp(FIREBASE_CONFIG);
      console.log("[dashboard] Firebase initialized");
      return true;
    }
    console.warn("[dashboard] No FIREBASE_CONFIG — Firebase not initialized");
    return false;
  }
  return true;
}

// ── Auth ───────────────────────────────────────────────────────────
const user = ref(null);
const authReady = ref(false);

function initAuth() {
  return new Promise((resolve) => {
    if (!ensureFirebase() || !firebase.auth) {
      authReady.value = true;
      resolve(null);
      return;
    }
    firebase.auth().onAuthStateChanged((u) => {
      user.value = u;
      authReady.value = true;
      resolve(u);
    });
  });
}

// ── Firestore ──────────────────────────────────────────────────────
let _db = null;
function db() {
  if (_db) return _db;
  if (!ensureFirebase()) return null;
  try {
    _db = firebase.firestore();
    console.log("[dashboard] Firestore connected");
    return _db;
  } catch (e) {
    console.error("[dashboard] Firestore init error:", e.message);
    return null;
  }
}

async function signIn() {
  const provider = new firebase.auth.GoogleAuthProvider();
  try {
    await firebase.auth().signInWithPopup(provider);
  } catch (e) {
    console.error("[dashboard] Sign-in failed:", e.message);
  }
}

function signOut() {
  firebase.auth().signOut();
}

// ── Studies ────────────────────────────────────────────────────────
const studies = ref([]);
const activeStudyId = ref(null);

async function loadStudies() {
  const d = db();
  if (!d) { console.warn("[dashboard] Firestore not available — cannot load studies"); return; }
  try {
    const snap = await d.collection(COLLECTION)
      .orderBy("created_at", "desc").get();
    studies.value = snap.docs.map(d => ({ id: d.id, ...d.data() }))
      .filter(s => s.status !== "archived");
    console.log("[dashboard] Loaded", studies.value.length, "studies");
  } catch (e) {
    console.error("[dashboard] loadStudies failed:", e.message, e);
    // Firestore might need an index — show the error link
    if (e.message && e.message.includes("index")) {
      console.warn("[dashboard] Create the required Firestore index:", e.message);
    }
  }
}

async function createStudy(name) {
  const d = db();
  if (!d || !user.value) return null;
  const id = name.trim();
  if (!id) return null;
  await d.collection(COLLECTION).doc(id).set({
    name: name.trim(),
    description: "",
    owner: user.value.uid,
    status: "active",
    created_at: firebase.firestore.FieldValue.serverTimestamp(),
  });
  await loadStudies();
  return id;
}

async function archiveStudy(id) {
  const d = db();
  if (!d || !user.value) return;
  await d.collection(COLLECTION).doc(id).update({ status: "archived" });
  await loadStudies();
  if (activeStudyId.value === id) activeStudyId.value = null;
}

async function restoreStudy(id) {
  const d = db();
  if (!d || !user.value) return;
  await d.collection(COLLECTION).doc(id).update({ status: "active" });
  await loadStudies();
}

// ── Experiments ────────────────────────────────────────────────────
const experiments = ref([]);
const activeExperimentId = ref(null);
const studyExperiments = ref({});  // studyId -> [{id, name, ...}]

async function loadAllExperiments() {
  const d = db();
  if (!d) return;
  const map = {};
  for (const s of studies.value) {
    try {
      const snap = await d.collection(COLLECTION).doc(s.id)
        .collection("experiments").orderBy("created_at", "desc").limit(3).get();
      map[s.id] = snap.docs.map(d => ({ id: d.id, ...d.data() }))
        .filter(e => e.status !== "archived");
    } catch (e) { map[s.id] = []; }
  }
  studyExperiments.value = map;
}

async function loadExperiments() {
  const d = db();
  if (!d || !activeStudyId.value) { experiments.value = []; return; }
  const snap = await d.collection(COLLECTION)
    .doc(activeStudyId.value).collection("experiments")
    .orderBy("created_at", "desc").get();
  experiments.value = snap.docs.map(d => ({ id: d.id, ...d.data() }))
    .filter(e => e.status !== "archived")
    .filter(e => e.status !== "archived");
}

async function createExperiment(name) {
  const d = db();
  if (!d || !activeStudyId.value) return null;
  const id = name.trim();
  if (!id) return null;
  await d.collection(COLLECTION).doc(activeStudyId.value)
    .collection("experiments").doc(id).set({
      name: name.trim(),
      description: "",
      created_at: firebase.firestore.FieldValue.serverTimestamp(),
      status: "active",
      total_games: 0,
      total_kills: 0,
      total_ejections: 0,
      by_winner: { crewmates: 0, imposters: 0, timeout: 0, token_limit: 0 },
      players: [],
    });
  await loadExperiments();
  return id;
}

async function archiveExperiment(id) {
  const d = db();
  if (!d || !activeStudyId.value || !user.value) return;
  await d.collection(COLLECTION).doc(activeStudyId.value)
    .collection("experiments").doc(id).update({ status: "archived" });
  await loadExperiments();
  if (activeExperimentId.value === id) activeExperimentId.value = null;
}

async function restoreExperiment(id) {
  const d = db();
  if (!d || !activeStudyId.value || !user.value) return;
  await d.collection(COLLECTION).doc(activeStudyId.value)
    .collection("experiments").doc(id).update({ status: "active" });
  await loadExperiments();
}

async function setDescription(type, id, expId, desc) {
  const d = db();
  if (!d || !user.value) return;
  const ref = type === "study"
    ? d.collection(COLLECTION).doc(id)
    : d.collection(COLLECTION).doc(id).collection("experiments").doc(expId);
  await ref.update({ description: desc || "" });
}

// ── Game data ──────────────────────────────────────────────────────
const stats = ref(null);
const games = ref([]);
const statusKind = ref("idle");
const statusText = ref("waiting for experiment data");
const lastSync = ref("");

async function fetchData() {
  const d = db();
  if (!d || !activeStudyId.value || !activeExperimentId.value) return false;
  try {
    const docRef = d.collection(COLLECTION).doc(activeStudyId.value)
      .collection("experiments").doc(activeExperimentId.value);
    const snap = await docRef.get();
    if (snap.exists) {
      stats.value = snap.data();
    }

    const gamesSnap = await docRef.collection("games").orderBy("ended_at").get();
    games.value = [];
    gamesSnap.forEach(doc => games.value.push(doc.data()));

    statusKind.value = "ok";
    statusText.value = `${stats.value?.total_games || 0} games · ${activeExperimentId.value}`;
    lastSync.value = "last sync " + new Date().toLocaleTimeString();
    return true;
  } catch (e) {
    statusKind.value = "error";
    statusText.value = "Fetch failed: " + e.message;
    return false;
  }
}

// ── Server watch ────────────────────────────────────────────────────
const servers = ref([]);
let _serverUnsub = null;

function startServerWatch() {
  const d = db();
  if (!d) return () => {};
  if (_serverUnsub) _serverUnsub();
  _serverUnsub = d.collection("servers").onSnapshot(
    snap => {
      servers.value = snap.docs.map(d => ({ id: d.id, ...d.data() }));
    },
    err => {
      // Collection or rules may not exist yet — silently ignore
      if (!err.message?.includes?.("permission") && !err.code?.includes?.("permission")) {
        console.warn("[dashboard] Server watch error:", err.message);
      }
      servers.value = [];
    }
  );
  return _serverUnsub;
}

function stopServerWatch() {
  if (_serverUnsub) { _serverUnsub(); _serverUnsub = null; }
}

// ── User permissions ────────────────────────────────────────────────
const userPermissions = ref(null);
const canRunExperiments = computed(() =>
  userPermissions.value?.can_run_experiments === true
);
const isAdmin = computed(() =>
  userPermissions.value?.is_admin === true
);

async function loadUserPermissions(uid) {
  if (!uid) { userPermissions.value = null; return; }
  const d = db();
  if (!d) return;
  try {
    const snap = await d.collection("users").doc(uid).get();
    if (snap.exists) {
      userPermissions.value = snap.data();
      return;
    }
    // Doc genuinely does not exist — create via transaction so a
    // concurrent creator can never be overwritten.
    try {
      await d.runTransaction(async (txn) => {
        const fresh = await txn.get(d.collection("users").doc(uid));
        if (!fresh.exists) {
          txn.set(d.collection("users").doc(uid), {
            uid: uid,
            email: user.value?.email || "",
            display_name: user.value?.displayName || "",
            can_run_experiments: false,
            created_at: firebase.firestore.FieldValue.serverTimestamp(),
          });
        }
      });
    } catch (e) {
      if (!e.message?.includes?.("permission") && !e.code?.includes?.("permission")) {
        console.warn("[dashboard] loadUserPermissions create failed:", e.message);
      }
    }
    userPermissions.value = { can_run_experiments: false };
    return;
  } catch (e) {
    // READ FAILED — never attempt to write here. A failed read is NOT
    // evidence the doc is missing; overwriting would wipe permissions
    // (this was wiping is_admin/can_run_experiments for real users).
    if (!e.message?.includes?.("permission") && !e.code?.includes?.("permission")) {
      console.warn("[dashboard] loadUserPermissions read failed:", e.message);
    }
    userPermissions.value = null; // unknown state — UI treats as no perms
  }
}

// ── Jobs ────────────────────────────────────────────────────────────
const jobs = ref([]);
let _jobsUnsub = null;

function watchJobsForExperiment(studyId, expCode) {
  const d = db();
  if (!d) return () => {};
  if (_jobsUnsub) _jobsUnsub();
  _jobsUnsub = d.collection("jobs")
    .where("study_id", "==", studyId)
    .where("experiment_code", "==", expCode)
    .orderBy("created_at", "desc")
    .limit(10)
    .onSnapshot(
      snap => {
        jobs.value = snap.docs.map(d => ({ id: d.id, ...d.data() }));
      },
      err => {
        // Log the full error so the user can create the required index
        console.warn("[dashboard] Job watch error:", err.message || err);
        if (err.message && err.message.includes("index")) {
          console.warn("[dashboard] Create the required Firestore index:", err.message);
        }
        jobs.value = [];
      }
    );
  return _jobsUnsub;
}

function unwatchJobs() {
  if (_jobsUnsub) { _jobsUnsub(); _jobsUnsub = null; }
}

// ── All jobs (global view, no study/experiment filter) ──────────────
const allJobs = ref([]);
let _allJobsUnsub = null;

function watchAllJobs() {
  const d = db();
  if (!d) return () => {};
  if (_allJobsUnsub) _allJobsUnsub();
  _allJobsUnsub = d.collection("jobs")
    .orderBy("created_at", "desc")
    .limit(50)
    .onSnapshot(
      snap => { allJobs.value = snap.docs.map(d => ({ id: d.id, ...d.data() })); },
      err => {
        console.warn("[dashboard] All jobs watch error:", err.message || err);
        if (err.message && err.message.includes("index")) {
          console.warn("[dashboard] Create the required Firestore index:", err.message);
        }
      }
    );
  return _allJobsUnsub;
}

function stopAllJobsWatch() {
  if (_allJobsUnsub) { _allJobsUnsub(); _allJobsUnsub = null; }
}

// Per-trial status for the job detail popup (lives on the experiment doc)
async function loadExperimentTrials(studyId, expId) {
  const d = db();
  const empty = { list: [], claimedBy: {}, completedBy: {}, versions: {}, errors: {} };
  if (!d) return empty;
  try {
    const snap = await d.collection(COLLECTION).doc(studyId)
      .collection("experiments").doc(expId).get({ source: "server" });
    if (!snap.exists) return empty;
    const data = snap.data();
    return {
      list: data.trials || [],
      claimedBy: data.trial_claimed_by || {},
      completedBy: data.trial_completed_by || {},
      versions: data.trial_versions || {},
      errors: data.trial_errors || {},
    };
  } catch (e) {
    console.warn("[dashboard] loadExperimentTrials failed:", e.message);
    return empty;
  }
}

// Jobs claimed by a specific server (for the server-monitor popup).
// Single-field equality query — no composite index required; sorted client-side.
async function loadServerJobs(serverName) {
  const d = db();
  if (!d || !serverName) return [];
  try {
    const snap = await d.collection("jobs")
      .where("claimed_by", "==", serverName)
      .limit(20)
      .get({ source: "server" });
    const jobs = snap.docs.map(x => ({ id: x.id, ...x.data() }));
    jobs.sort((a, b) => {
      const ta = a.created_at?.toMillis?.() || 0;
      const tb = b.created_at?.toMillis?.() || 0;
      return tb - ta;
    });
    return jobs;
  } catch (e) {
    console.warn("[dashboard] loadServerJobs failed:", e.message);
    return [];
  }
}

// Ask the server running a job to expose its render relay (see
// server_handler._maybe_start_render_for_job). The job doc's `render`
// field is published by the server when the relay is up.
async function requestJobRender(jobId) {
  const d = db();
  if (!d || !user.value) throw new Error("Not authenticated");
  await d.collection("jobs").doc(jobId).update({ render_requested: true });
  console.log("[dashboard] Render requested for job", jobId);
}

async function loadJob(jobId) {
  const d = db();
  if (!d) return null;
  try {
    const snap = await d.collection("jobs").doc(jobId).get({ source: "server" });
    return snap.exists ? { id: snap.id, ...snap.data() } : null;
  } catch (e) {
    console.warn("[dashboard] loadJob failed:", e.message);
    return null;
  }
}

async function queueJob({ studyId, experimentCode }) {
  const d = db();
  if (!d || !user.value) throw new Error("Not authenticated");
  // Job just points at an experiment — the experiment's trials array
  // determines how many individual games (trials) get run.
  const docRef = await d.collection("jobs").add({
    study_id: studyId,
    experiment_code: experimentCode,
    created_by: user.value.uid,
    created_at: firebase.firestore.FieldValue.serverTimestamp(),
    status: "queued",
    claimed_by: null,
    claimed_at: null,
    started_at: null,
    finished_at: null,
    error: null,
    result: null,
  });
  return docRef.id;
}

// ── Duplication ────────────────────────────────────────────────

async function duplicateStudy(studyId, includeData) {
  const d = db();
  if (!d || !user.value) throw new Error("Not authenticated");
  const srcRef = d.collection(COLLECTION).doc(studyId);
  const srcSnap = await srcRef.get();
  if (!srcSnap.exists) throw new Error("Study not found");
  const src = srcSnap.data();

  const newId = studyId + "-copy-" + Date.now().toString(36);
  await d.collection(COLLECTION).doc(newId).set({
    name: (src.name || studyId) + " (copy)",
    description: src.description || "",
    owner: user.value.uid,
    status: "active",
    created_at: firebase.firestore.FieldValue.serverTimestamp(),
  });

  // Copy experiments
  const expsSnap = await srcRef.collection("experiments").get();
  for (const e of expsSnap.docs) {
    await duplicateExperimentInternal(e.ref, d.collection(COLLECTION).doc(newId)
      .collection("experiments").doc(e.id), e.data(), includeData);
  }
  await loadStudies();
  return newId;
}

async function duplicateExperiment(studyId, expId, includeData) {
  const d = db();
  if (!d || !user.value) throw new Error("Not authenticated");
  const srcExp = d.collection(COLLECTION).doc(studyId)
    .collection("experiments").doc(expId);
  const srcSnap = await srcExp.get();
  if (!srcSnap.exists) throw new Error("Experiment not found");
  const data = srcSnap.data();

  const newExpId = expId + "-copy-" + Date.now().toString(36);
  const dstExp = d.collection(COLLECTION).doc(studyId)
    .collection("experiments").doc(newExpId);
  await duplicateExperimentInternal(srcExp, dstExp, data, includeData);
  await loadExperiments();
  return newExpId;
}

async function duplicateExperimentInternal(srcExpRef, dstExpRef, ed, includeData) {
  // Base experiment doc (settings)
  await dstExpRef.set({
    name: ed.name || "copy",
    description: ed.description || "",
    config: ed.config || null,
    created_at: firebase.firestore.FieldValue.serverTimestamp(),
    status: "active",
    total_games: includeData ? (ed.total_games || 0) : 0,
    total_kills: includeData ? (ed.total_kills || 0) : 0,
    total_ejections: includeData ? (ed.total_ejections || 0) : 0,
    by_winner: includeData ? (ed.by_winner || {}) : {},
    players: includeData ? (ed.players || []) : [],
    trials: includeData ? (ed.trials || []) : [],
  });

  if (!includeData) return;

  // Copy games + trace docs (batched, 400 writes per batch)
  const gamesSnap = await srcExpRef.collection("games").get();
  let batch = db().batch();
  let ops = 0;
  const flush = async () => {
    if (ops > 0) { await batch.commit(); batch = db().batch(); ops = 0; }
  };
  for (const g of gamesSnap.docs) {
    batch.set(dstExpRef.collection("games").doc(g.id), g.data());
    ops++;
    const tracesSnap = await g.ref.collection("trace").get();
    for (const t of tracesSnap.docs) {
      batch.set(dstExpRef.collection("games").doc(g.id)
        .collection("trace").doc(t.id), t.data());
      ops++;
      if (ops >= 400) await flush();
    }
    if (ops >= 400) await flush();
  }
  await flush();
}

async function clearExperimentData(studyId, expId) {
  const d = db();
  if (!d || !user.value) throw new Error("Not authenticated");
  const expRef = d.collection(COLLECTION).doc(studyId)
    .collection("experiments").doc(expId);
  const archiveRef = expRef.collection("archived_data").doc();

  // Read current stats
  const snap = await expRef.get();
  if (!snap.exists) throw new Error("Experiment not found");
  const data = snap.data();

  // Archive stats, games, and trial metadata
  const archive = {
    archived_at: firebase.firestore.FieldValue.serverTimestamp(),
    total_games: data.total_games || 0,
    total_kills: data.total_kills || 0,
    total_ejections: data.total_ejections || 0,
    by_winner: data.by_winner || {},
    players: data.players || [],
    trials: data.trials || [],
    trial_claimed_at: data.trial_claimed_at || {},
    trial_claimed_by: data.trial_claimed_by || {},
    trial_completed_at: data.trial_completed_at || {},
    trial_completed_by: data.trial_completed_by || {},
    trial_versions: data.trial_versions || {},
    trial_errors: data.trial_errors || {},
  };
  await archiveRef.set(archive);

  // Move games subcollection
  const gamesSnap = await expRef.collection("games").get();
  const batch = d.batch();
  for (const g of gamesSnap.docs) {
    batch.set(archiveRef.collection("games").doc(g.id), g.data());
    batch.delete(g.ref);
  }
  await batch.commit();

  // Reset stats + trials + trial metadata (fresh run-ready state).
  // cleared_at lets servers discard in-flight trials/games that belong
  // to the wiped run instead of resurrecting them after the clear.
  const del = firebase.firestore.FieldValue.delete();
  await expRef.update({
    total_games: 0,
    total_kills: 0,
    total_ejections: 0,
    by_winner: {},
    players: [],
    trials: [],
    trial_claimed_at: del,
    trial_claimed_by: del,
    trial_completed_at: del,
    trial_completed_by: del,
    trial_versions: del,
    trial_errors: del,
    cleared_at: firebase.firestore.FieldValue.serverTimestamp(),
  });
  console.log("[dashboard] Data archived to", archiveRef.path);
}

// ── Game traces ────────────────────────────────────────────────────

async function loadGameTrace(studyId, expId, gameId) {
  const d = db();
  if (!d) return null;
  try {
    const ref = d.collection(COLLECTION).doc(studyId)
      .collection("experiments").doc(expId)
      .collection("games").doc(gameId)
      .collection("trace").doc("raw");
    const snap = await ref.get();
    if (!snap.exists) return null;
    const meta = snap.data();

    // Primary: fetch from GCS public URL
    if (meta.url) {
      const resp = await fetch(meta.url);
      if (resp.ok) return await resp.text();
      console.warn("[dashboard] GCS fetch failed, trying fallback...");
    }
    // Fallback: inline data stored in Firestore
    if (meta.data) return meta.data;
    // Legacy format
    return meta.trace || JSON.stringify(meta);
  } catch (e) {
    console.warn("[dashboard] loadGameTrace failed:", e.message);
  }
  return null;
}

// ── Admin ──────────────────────────────────────────────────────────

async function listAllUsers() {
  const d = db();
  if (!d) return [];
  const snap = await d.collection("users").get();
  return snap.docs.map(d => ({ uid: d.id, ...d.data() }));
}

async function updateUserPermissions(uid, updates) {
  const d = db();
  if (!d || !user.value) throw new Error("Not authenticated");
  // Only allow setting specific fields from client
  const allowed = {};
  if ("can_run_experiments" in updates) allowed.can_run_experiments = updates.can_run_experiments;
  if ("is_admin" in updates) allowed.is_admin = updates.is_admin;
  if (Object.keys(allowed).length === 0) return;
  await d.collection("users").doc(uid).update(allowed);
  console.log("[dashboard] Updated user", uid, allowed);
}

// ── Public landing page (aggregated live stats, no auth required) ────
const publicExperiments = ref([]);
const publicLoading = ref(false);

async function loadPublicExperiments() {
  const d = db();
  if (!d) return;
  publicLoading.value = true;
  try {
    const studiesSnap = await d.collection(COLLECTION)
      .orderBy("created_at", "desc").get();
    const activeStudies = studiesSnap.docs
      .map(doc => ({ id: doc.id, ...doc.data() }))
      .filter(s => s.status !== "archived");

    const list = [];
    for (const s of activeStudies) {
      const expSnap = await d.collection(COLLECTION).doc(s.id)
        .collection("experiments").orderBy("created_at", "desc").get();
      for (const expDoc of expSnap.docs) {
        const data = expDoc.data();
        if (data.status === "archived") continue;
        if (!data.total_games) continue;

        let recent_games = [];
        try {
          const gamesSnap = await d.collection(COLLECTION).doc(s.id)
            .collection("experiments").doc(expDoc.id)
            .collection("games").orderBy("ended_at", "desc").limit(6).get();
          recent_games = gamesSnap.docs.map(g => g.data()).reverse();
        } catch (e) { /* index or read issue — skip ticker for this experiment */ }

        list.push({ studyId: s.id, studyName: s.name, id: expDoc.id, ...data, recent_games });
      }
    }
    publicExperiments.value = list;
  } catch (e) {
    console.error("[dashboard] loadPublicExperiments failed:", e.message);
  } finally {
    publicLoading.value = false;
  }
}

// ── Config from Firestore ───────────────────────────────────────────
function configFingerprint(cfg) {
  if (!cfg || typeof cfg !== "object") return String(cfg);
  const keys = Object.keys(cfg).sort().join(",");
  return `${cfg.type || "?"}::${cfg.class || "?"} trial_count=${cfg.trial_count ?? "—"} keys=[${keys}]`;
}

async function saveExperimentConfig(studyId, expId, configObj) {
  const d = db();
  if (!d || !user.value) throw new Error("Not authenticated");
  const path = `${COLLECTION}/${studyId}/experiments/${expId}`;
  const fp = configFingerprint(configObj);
  console.log(`[dashboard] save → ${path}: ${fp}`);
  const ref = d.collection(COLLECTION).doc(studyId)
    .collection("experiments").doc(expId);

  // Read the current doc so we can remove any stale keys left inside `config`
  const snap = await ref.get({ source: "server" });
  const oldConfig = snap.exists ? snap.data().config : null;

  // Firestore forbids updating a map and its children in one write, so
  // delete stale keys first (separate update), then write the new config.
  if (oldConfig && typeof oldConfig === "object" && !Array.isArray(oldConfig)) {
    const deletes = {};
    for (const key of Object.keys(oldConfig)) {
      if (!(key in configObj)) {
        deletes[`config.${key}`] = firebase.firestore.FieldValue.delete();
      }
    }
    if (Object.keys(deletes).length) {
      console.log(`[dashboard] removing stale config keys: ${Object.keys(deletes).map(k => k.replace("config.", "")).join(", ")}`);
      await ref.update(deletes);
    }
  }
  await ref.update({ config: configObj });

  // Verify against the SERVER — bypasses any local cache, so a write that
  // didn't actually commit fails loudly here instead of silently reverting.
  const after = await ref.get({ source: "server" });
  const stored = after.exists ? after.data().config : null;
  const storedFp = configFingerprint(stored);
  if (storedFp !== fp) {
    throw new Error(
      `write did not persist — DB has ${storedFp} right after writing ${fp}. ` +
      "Check the Network tab for the update() response (rules deny? offline queue?).");
  }
  console.log(`[dashboard] save verified → ${path}`);
}

async function loadExperimentConfig(studyId, expId) {
  const d = db();
  if (!d) return null;
  try {
    const path = `${COLLECTION}/${studyId}/experiments/${expId}`;
    const snap = await d.collection(COLLECTION).doc(studyId)
      .collection("experiments").doc(expId).get({ source: "server" });
    if (snap.exists) {
      const data = snap.data();
      console.log(`[dashboard] load ← ${path}: ${configFingerprint(data.config)}`);
      return data.config || null;
    }
    console.log(`[dashboard] load ← ${path}: (doc does not exist)`);
  } catch (e) {
    console.warn("[dashboard] loadExperimentConfig failed:", e.message);
  }
  return null;
}

export function useFirestore() {
  return {
    // auth
    user, authReady, initAuth, signIn, signOut,
    // studies
    studies, activeStudyId, loadStudies, createStudy, archiveStudy, restoreStudy,
    // experiments
    experiments, activeExperimentId, studyExperiments,
    loadAllExperiments, loadExperiments, createExperiment, archiveExperiment, restoreExperiment,
    setDescription,
    // data
    stats, games, statusKind, statusText, lastSync,
    fetchData,
    // servers
    servers, startServerWatch, stopServerWatch,
    // user permissions
    userPermissions, canRunExperiments, isAdmin, loadUserPermissions,
    listAllUsers, updateUserPermissions,
    loadGameTrace,
    // jobs
    jobs, watchJobsForExperiment, unwatchJobs, queueJob,
    allJobs, watchAllJobs, stopAllJobsWatch, loadExperimentTrials, loadServerJobs,
    requestJobRender, loadJob,
    // config
    loadExperimentConfig, saveExperimentConfig, clearExperimentData,
    // duplication
    duplicateStudy, duplicateExperiment,
    // public landing page
    publicExperiments, publicLoading, loadPublicExperiments,
  };
}
