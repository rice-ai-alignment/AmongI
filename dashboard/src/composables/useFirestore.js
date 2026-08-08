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
  } catch (e) {
    // Rules may not be deployed yet — continue to try creation
    if (!e.message?.includes?.("permission") && !e.code?.includes?.("permission")) {
      console.warn("[dashboard] loadUserPermissions read failed:", e.message);
    }
  }
  // Either doc doesn't exist or read was denied — try to create it
  try {
    await d.collection("users").doc(uid).set({
      uid: uid,
      email: user.value?.email || "",
      display_name: user.value?.displayName || "",
      can_run_experiments: false,
      created_at: firebase.firestore.FieldValue.serverTimestamp(),
    });
  } catch (e) {
    // Rules may not allow creation yet — just use a local default
    if (!e.message?.includes?.("permission") && !e.code?.includes?.("permission")) {
      console.warn("[dashboard] loadUserPermissions create failed:", e.message);
    }
  }
  userPermissions.value = { can_run_experiments: false };
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
        // Index or rules may not exist yet — silently ignore
        if (!err.message?.includes?.("permission") && !err.message?.includes?.("index")) {
          console.warn("[dashboard] Job watch error:", err.message);
        }
        jobs.value = [];
      }
    );
  return _jobsUnsub;
}

function unwatchJobs() {
  if (_jobsUnsub) { _jobsUnsub(); _jobsUnsub = null; }
}

async function queueJob({ studyId, experimentCode, config, maxGames }) {
  const d = db();
  if (!d || !user.value) throw new Error("Not authenticated");
  const docRef = await d.collection("jobs").add({
    study_id: studyId,
    experiment_code: experimentCode,
    config: config || {},
    max_games: maxGames || 1,
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

// ── Config from Firestore ───────────────────────────────────────────
async function loadExperimentConfig(studyId, expId) {
  const d = db();
  if (!d) return null;
  try {
    const snap = await d.collection(COLLECTION).doc(studyId)
      .collection("experiments").doc(expId).get();
    if (snap.exists) {
      const data = snap.data();
      return data.config || null;
    }
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
    userPermissions, canRunExperiments, loadUserPermissions,
    // jobs
    jobs, watchJobsForExperiment, unwatchJobs, queueJob,
    // config
    loadExperimentConfig,
  };
}
