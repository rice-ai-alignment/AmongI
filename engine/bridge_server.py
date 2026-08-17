#!/usr/bin/env python3
"""bridge_server.py — Tails the engine's JSONL log files and pushes finished-game
recaps + recent chats to Firestore so the dashboard can read them directly.

Usage:
    python bridge_server.py [--log-dir DIR] [--interval SEC]

No HTTP endpoints — everything flows through Firestore.
"""

from __future__ import annotations

import argparse
import asyncio
import glob as globmod
import json
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

# ── Firestore ────────────────────────────────────────────────────────────
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    HAS_FIRESTORE = True
except ImportError:
    HAS_FIRESTORE = False

STUDIES_COLLECTION = "studies"
STUDY_ID = os.getenv("STUDY_ID", "")
EXPERIMENT_CODE = os.getenv("EXPERIMENT_CODE", "")
FIREBASE_CRED_PATH = os.getenv("FIREBASE_CRED_PATH", "firebase-key.json")
GCS_BUCKET = "raia-labs.firebasestorage.app"  # Firebase Storage bucket (gs://raia-labs.firebasestorage.app)
_firestore_ready = False


def _to_ms(v) -> Optional[int]:
    """Convert a Firestore timestamp / datetime / ISO string to epoch ms."""
    if v is None:
        return None
    try:
        if hasattr(v, "timestamp"):          # Firestore datetime
            return int(v.timestamp() * 1000)
        if isinstance(v, str):
            s = v.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
    except Exception:
        pass
    return None


def _upload_to_gcs(blob_path: str, data: str, content_type: str = "text/plain") -> Optional[str]:
    """Upload a string to Firebase Storage via its REST API.

    Uses the firebase-admin service account for auth (no google-cloud-storage
    package needed) and returns the public download URL, or None on failure.
    """
    if not GCS_BUCKET:
        return None
    try:
        import google.auth.transport.requests
        import firebase_admin
        from urllib.parse import quote
        from urllib.request import Request, urlopen

        # Token from the firebase-admin credential (firebase-key.json)
        cred = firebase_admin.get_app().credential.get_credential()
        cred.refresh(google.auth.transport.requests.Request())
        token = cred.token
        if not token:
            print("[Bridge] Storage upload failed: no access token")
            return None

        encoded = quote(blob_path, safe="")
        upload_url = f"https://firebasestorage.googleapis.com/v0/b/{GCS_BUCKET}/o?name={encoded}"
        req = Request(
            upload_url, data=data.encode("utf-8"), method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
            })
        resp = json.loads(urlopen(req, timeout=60).read().decode("utf-8"))

        # Public URL — the download token grants access, and storage.rules
        # allows public reads for per-trial folders ({study}/{exp}/{game}/).
        download_url = f"https://firebasestorage.googleapis.com/v0/b/{GCS_BUCKET}/o/{encoded}?alt=media"
        tokens = (resp.get("downloadTokens") or "").split(",")
        if tokens and tokens[0]:
            download_url += f"&token={tokens[0]}"
        return download_url
    except Exception as e:
        print(f"[Bridge] GCS upload failed for {blob_path}: {e}")
        return None


def check_study_experiment(study: str, experiment: str) -> bool:
    """Verify that the study and experiment documents exist in Firestore.

    Returns True if both exist.  Prints a clear error message and
    returns False if either is missing or Firestore is unavailable.
    """
    if not _firestore_ready:
        print("[Bridge] Firestore not initialised — run init_firestore() first")
        return False
    if not study or not experiment:
        print("[Bridge] STUDY_ID and EXPERIMENT_CODE are required")
        return False
    try:
        db = firestore.client()
        study_ref = db.collection(STUDIES_COLLECTION).document(study)
        study_doc = study_ref.get()
        if not study_doc.exists:
            print(f"[Bridge] Study {study!r} does not exist in Firestore")
            print(f"         Create it in the dashboard first: studies/{study}")
            return False
        exp_ref = study_ref.collection("experiments").document(experiment)
        exp_doc = exp_ref.get()
        if not exp_doc.exists:
            print(f"[Bridge] Experiment {experiment!r} does not exist under study {study!r}")
            print(f"         Create it in the dashboard first: studies/{study}/experiments/{experiment}")
            return False
        print(f"[Bridge] Study + experiment verified: studies/{study}/experiments/{experiment}")
        return True
    except Exception as e:
        print(f"[Bridge] Firestore check failed: {e}")
        return False


def init_firestore():
    global _firestore_ready
    if not HAS_FIRESTORE:
        print("[Bridge] firebase_admin not installed — skipping Firestore")
        return False
    try:
        cred = credentials.Certificate(FIREBASE_CRED_PATH)
        firebase_admin.initialize_app(cred)
        _firestore_ready = True
        print("[Bridge] Firestore connected")
        return True
    except Exception as e:
        print(f"[Bridge] Firestore init failed: {e}")
        return False


# ── Log tailer ──────────────────────────────────────────────────────────

class LogStore:
    """Tails the session JSONL log and pushes new game data to Firestore."""

    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self.lock = Lock()
        self.session_id: Optional[str] = None
        self.current_game_id: Optional[str] = None
        self.games: list[dict] = []
        self._session_log_path: Optional[str] = None
        self._file_pos: int = 0
        self._pushed_game_ids: set = set()
        self._pushed_config_game_ids: set = set()
        self._session_dir: Optional[str] = None

    def _find_latest_log(self) -> Optional[str]:
        pattern = os.path.join(self.log_dir, "SESSION-*.jsonl")
        files = sorted(globmod.glob(pattern), reverse=True)
        return files[0] if files else None

    def load_logs(self):
        """Initial sweep of the latest session log."""
        path = self._find_latest_log()
        if not path:
            print("[Bridge] No session logs found in", self.log_dir)
            return
        self._session_log_path = path
        self._session_dir = os.path.dirname(path)
        stem = os.path.splitext(os.path.basename(path))[0]
        session_subdir = os.path.join(os.path.dirname(path), stem)
        if os.path.isdir(session_subdir):
            self._session_dir = session_subdir
        print(f"[Bridge] Tailing: {path}")
        with self.lock:
            self._read_to_end(path)
        print(f"[Bridge] Initial sweep: {len(self.games)} games")

    def tail(self):
        """Check for new session logs and read new lines."""
        # Detect new session log files
        latest = self._find_latest_log()
        if latest and latest != self._session_log_path:
            print(f"[Bridge] New session: {latest}")
            self._session_log_path = latest
            # Session dir is the subdirectory named after the session file stem
            # e.g. log/SESSION-ts.jsonl → log/SESSION-ts/
            stem = os.path.splitext(os.path.basename(latest))[0]
            self._session_dir = os.path.join(os.path.dirname(latest), stem)
            self._file_pos = 0
            with self.lock:
                self._read_to_end(latest)
            return

        if not self._session_log_path:
            return
        try:
            size = os.path.getsize(self._session_log_path)
            if size <= self._file_pos:
                return
            with self.lock:
                self._read_to_end(self._session_log_path)
        except OSError:
            pass

    def _read_to_end(self, path: str):
        """Read all new lines from path starting at _file_pos."""
        push = _firestore_ready  # read at call time, not definition time
        with open(path, "r", encoding="utf-8") as f:
            f.seek(self._file_pos)
            for line in f:
                self._process_line(line, push=push)
        self._file_pos = os.path.getsize(path)

    def _process_line(self, line: str, push: bool = False):
        line = line.strip()
        if not line:
            return
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            return

        sid = ev.get("session")
        if sid:
            self.session_id = sid
        gid = ev.get("game_id")
        if gid:
            self.current_game_id = gid

        if ev.get("type") == "game_end" and ev.get("recap"):
            recap = dict(ev["recap"])
            recap.setdefault("schema_version", "1.0")
            recap.setdefault("session_id", ev.get("session") or self.session_id)
            recap.setdefault("game_id", ev.get("game_id") or self.current_game_id)
            recap.setdefault("started_at", None)
            recap.setdefault("ended_at", ev.get("timestamp"))
            recap.setdefault("duration_sec", None)
            for p in recap.get("players", []):
                p.setdefault("color", None)
            self.games.append(recap)
            if push:
                self._push_game(recap)

    # ── Firestore writes ──────────────────────────────────────────────

    def _experiment_doc_ref(self):
        """Return Firestore DocumentReference for the active experiment."""
        db = firestore.client()
        study = os.getenv("STUDY_ID", "") or STUDY_ID
        exp = os.getenv("EXPERIMENT_CODE", "") or EXPERIMENT_CODE
        if study and exp:
            return db.collection(STUDIES_COLLECTION).document(study) \
                     .collection("experiments").document(exp)
        # Fallback: session-based temp name
        sid = self.session_id or "unknown"
        return db.collection(STUDIES_COLLECTION).document(sid.replace("SESSION-", "exp-"))

    def _push_config_for_game(self, game_id: str, game_ref):
        """Push per-game config.json to Firestore if present."""
        if not _firestore_ready or not self._session_dir:
            return
        if game_id in self._pushed_config_game_ids:
            return
        config_path = os.path.join(self._session_dir, game_id, "config.json")
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            game_ref.set({"config": config}, merge=True)
            self._pushed_config_game_ids.add(game_id)
            print(f"[Bridge] Pushed per-game config for {game_id}")
        except Exception as e:
            print(f"[Bridge] Config push failed: {e}")

    def _cleared_at_ms(self) -> Optional[int]:
        """Epoch ms of the experiment's cleared_at field, or None."""
        if not _firestore_ready:
            return None
        try:
            doc = self._experiment_doc_ref().get()
            if not doc.exists:
                return None
            return _to_ms(doc.to_dict().get("cleared_at"))
        except Exception:
            return None

    def _push_game(self, recap: dict):
        if not _firestore_ready:
            return
        try:
            game_id = recap.get("game_id", "unknown")
            if game_id in self._pushed_game_ids:
                return

            # If the experiment data was cleared after this game ended,
            # the result belongs to a wiped run — don't resurrect it.
            cleared_ms = self._cleared_at_ms()
            ended_ms = _to_ms(recap.get("ended_at"))
            if cleared_ms is not None and (ended_ms is None or ended_ms <= cleared_ms):
                print(f"[Bridge] Skipping {game_id} — experiment data was cleared after it ended")
                return

            # Local files live under the EventStore game id (e.g. GAME-001),
            # while the pushed doc id may be trial-based (e.g. TRIAL-000).
            log_game_id = recap.get("log_game_id") or game_id
            doc_ref = self._experiment_doc_ref()
            game_ref = doc_ref.collection("games").document(game_id)
            game_ref.set(recap)

            # Push per-game trace, logs, and config if available
            self._push_trace(log_game_id, game_id, game_ref)
            self._push_logs(log_game_id, game_id)
            self._push_config_for_game(log_game_id, game_ref)

            # Stats must not resurrect pre-clear games either
            games_after_clear = self.games
            if cleared_ms is not None:
                games_after_clear = [
                    g for g in self.games
                    if (ms := _to_ms(g.get("ended_at"))) is not None and ms > cleared_ms
                ]
            stats = compute_stats(games_after_clear, self.session_id)
            doc_ref.set(stats, merge=True)
            self._pushed_game_ids.add(game_id)
            print(f"[Bridge] Pushed {game_id} to {doc_ref.path} "
                  f"({stats['total_games']} games, {stats['total_kills']} kills)")
        except Exception as e:
            print(f"[Bridge] Firestore push failed: {e}")

    def _push_logs(self, log_game_id: str, game_id: str):
        """Upload per-trial raw logs (game JSONL + session JSONL) to GCS."""
        if not self._session_dir or not GCS_BUCKET:
            return
        study = os.getenv("STUDY_ID", "") or STUDY_ID
        exp = os.getenv("EXPERIMENT_CODE", "") or EXPERIMENT_CODE
        if not study or not exp:
            return

        # Per-game event log: {session_dir}/GAME-001.jsonl
        game_log = os.path.join(self._session_dir, f"{log_game_id}.jsonl")
        if os.path.exists(game_log):
            try:
                with open(game_log, "r") as f:
                    data = f.read()
                gcs_path = f"{study}/{exp}/{game_id}/game.jsonl"
                url = _upload_to_gcs(gcs_path, data, "application/jsonl")
                if url:
                    print(f"[Bridge] Game log → GCS: {url}")
            except Exception as e:
                print(f"[Bridge] Game log upload failed: {e}")

        # Session event log: {log_dir}/SESSION-*.jsonl (one session per trial)
        if self._session_log_path and os.path.exists(self._session_log_path):
            try:
                with open(self._session_log_path, "r") as f:
                    data = f.read()
                gcs_path = f"{study}/{exp}/{game_id}/session.jsonl"
                url = _upload_to_gcs(gcs_path, data, "application/jsonl")
                if url:
                    print(f"[Bridge] Session log → GCS: {url}")
            except Exception as e:
                print(f"[Bridge] Session log upload failed: {e}")

    def _push_trace(self, log_game_id: str, game_id: str, game_ref):
        """Push per-game trace.jsonl to GCS (primary) or Firestore (fallback)."""
        if not self._session_dir:
            return
        trace_path = os.path.join(self._session_dir, log_game_id, "trace.jsonl")
        if not os.path.exists(trace_path):
            return
        try:
            with open(trace_path, "r") as f:
                trace_data = f.read()
            # Parse pretty-printed JSON entries for summary
            trace_events = []
            for block in trace_data.split("\n\n"):
                block = block.strip()
                if not block:
                    continue
                try:
                    trace_events.append(json.loads(block))
                except json.JSONDecodeError:
                    continue
            summary = {
                "event_count": len(trace_events),
                "categories": list(set(e.get("category", "") for e in trace_events)),
                "tick_range": [min((e.get("tick", 0) for e in trace_events), default=0),
                               max((e.get("tick", 0) for e in trace_events), default=0)],
            }
            game_ref.collection("trace").document("summary").set(summary)

            # Upload raw trace to GCS, store public URL + size in Firestore
            study = os.getenv("STUDY_ID", "") or STUDY_ID
            exp = os.getenv("EXPERIMENT_CODE", "") or EXPERIMENT_CODE
            gcs_path = f"{study}/{exp}/{game_id}/trace.jsonl"
            public_url = _upload_to_gcs(gcs_path, trace_data, "application/jsonl")
            raw_doc = {
                "size": len(trace_data),
                "gcs_path": gcs_path,
            }
            if public_url:
                raw_doc["url"] = public_url
                print(f"[Bridge] Trace → GCS: {public_url}")
            else:
                # Fallback: store inline in Firestore (legacy, limited to ~1 MiB)
                if len(trace_data) < 900_000:
                    raw_doc["data"] = trace_data
                else:
                    print(f"[Bridge] Trace too large for Firestore fallback "
                          f"({len(trace_data)} bytes) — set GCS_BUCKET env var")
            game_ref.collection("trace").document("raw").set(raw_doc)
            print(f"[Bridge] Pushed trace for {game_id} ({len(trace_events)} events, {len(trace_data)} bytes)")
        except Exception as e:
            print(f"[Bridge] Trace push failed: {e}")

    def _compute_stats(self) -> dict:
        """Compute aggregated stats from all games."""
        return compute_stats(self.games, self.session_id)


def compute_stats(games: list[dict], session_id: str = "") -> dict:
    """Compute aggregated stats from a list of game recaps (module-level, reusable)."""
    by_winner: dict[str, int] = {}
    total_kills = 0
    total_ejections = 0
    player_stats: dict[str, dict] = {}

    for g in games:
        w = g.get("winner", "unknown")
        by_winner[w] = by_winner.get(w, 0) + 1
        total_kills += g.get("kills", 0)
        total_ejections += g.get("ejections", 0)

        for p in g.get("players", []):
            name = p.get("name", "unknown")
            role = p.get("role", p.get("imposter", ""))  # new field, fallback to old
            if name not in player_stats:
                player_stats[name] = {
                    "name": name, "role": role,
                    "games": 0, "wins": 0, "kills": 0,
                    "color": p.get("color"),
                }
            ps = player_stats[name]
            ps["games"] += 1
            ps["kills"] += p.get("kills", 0)
            # A win for this player: their role matches the winner group
            if role and str(role).lower() == str(w).lower():
                ps["wins"] += 1

    return {
        "total_games": len(games),
        "total_kills": total_kills,
        "total_ejections": total_ejections,
        "by_winner": by_winner,
        "players": sorted(player_stats.values(),
                          key=lambda p: (p["wins"] / max(p["games"], 1), p["games"]),
                          reverse=True),
        "session_id": session_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Main loop ──────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Among-I log tailer → Firestore")
    parser.add_argument("--log-dir", default="../log")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Seconds between log-tail checks")
    parser.add_argument("--study", default=os.getenv("STUDY_ID", ""),
                        help="Firestore study name")
    parser.add_argument("--experiment", default=os.getenv("EXPERIMENT_CODE", ""),
                        help="Firestore experiment name")
    args = parser.parse_args()
    if args.study:
        os.environ["STUDY_ID"] = args.study
    if args.experiment:
        os.environ["EXPERIMENT_CODE"] = args.experiment

    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), args.log_dir))
    print(f"[Bridge] Watching: {log_dir}")
    study = args.study or os.getenv("STUDY_ID", "")
    exp = args.experiment or os.getenv("EXPERIMENT_CODE", "")
    if study and exp:
        print(f"[Bridge] Target: studies/{study}/experiments/{exp}")

    store = LogStore(log_dir)
    store.load_logs()

    if HAS_FIRESTORE:
        init_firestore()

    print("[Bridge] Running — Ctrl+C to stop.")
    try:
        while True:
            store.tail()
            await asyncio.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[Bridge] Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
