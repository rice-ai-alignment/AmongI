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

FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "studies")
STUDY_ID = os.getenv("STUDY_ID", "")
EXPERIMENT_CODE = os.getenv("EXPERIMENT_CODE", "")
FIREBASE_CRED_PATH = os.getenv("FIREBASE_CRED_PATH", "firebase-key.json")
_firestore_ready = False


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
        study_ref = db.collection(FIRESTORE_COLLECTION).document(study)
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
        self._pushed_session_config: bool = False
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
        print(f"[Bridge] Tailing: {path}")
        with self.lock:
            self._read_to_end(path)
        print(f"[Bridge] Initial sweep: {len(self.games)} games")
        self._push_session_config()

    def tail(self):
        """Check for new session logs and read new lines."""
        # Detect new session log files
        latest = self._find_latest_log()
        if latest and latest != self._session_log_path:
            print(f"[Bridge] New session: {latest}")
            self._session_log_path = latest
            self._session_dir = os.path.dirname(latest)
            self._file_pos = 0
            self._pushed_session_config = False
            with self.lock:
                self._read_to_end(latest)
            self._push_session_config()
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
            return db.collection(FIRESTORE_COLLECTION).document(study) \
                     .collection("experiments").document(exp)
        # Fallback: session-based temp name
        sid = self.session_id or "unknown"
        return db.collection(FIRESTORE_COLLECTION).document(sid.replace("SESSION-", "exp-"))

    def _push_session_config(self):
        """Push session-level config.json to the experiment doc."""
        if not _firestore_ready or self._pushed_session_config or not self._session_dir:
            return
        config_path = os.path.join(self._session_dir, "config.json")
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            doc_ref = self._experiment_doc_ref()
            doc_ref.set({"config": config, "config_updated_at": datetime.now(timezone.utc).isoformat()}, merge=True)
            self._pushed_session_config = True
            print(f"[Bridge] Pushed session config to {doc_ref.path}")
        except Exception as e:
            print(f"[Bridge] Session config push failed: {e}")

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

    def _push_game(self, recap: dict):
        if not _firestore_ready:
            return
        try:
            game_id = recap.get("game_id", "unknown")
            if game_id in self._pushed_game_ids:
                return
            doc_ref = self._experiment_doc_ref()
            game_ref = doc_ref.collection("games").document(game_id)
            game_ref.set(recap)

            # Push per-game trace and config if available
            self._push_trace(game_id, game_ref)
            self._push_config_for_game(game_id, game_ref)

            stats = self._compute_stats()
            doc_ref.set(stats, merge=True)
            self._pushed_game_ids.add(game_id)
            print(f"[Bridge] Pushed {game_id} to {doc_ref.path} "
                  f"({stats['total_games']} games, {stats['total_kills']} kills)")
        except Exception as e:
            print(f"[Bridge] Firestore push failed: {e}")

    def _push_trace(self, game_id: str, game_ref):
        """Push per-game trace.jsonl to Firestore under the game document."""
        if not self._session_dir:
            return
        trace_path = os.path.join(self._session_dir, game_id, "trace.jsonl")
        if not os.path.exists(trace_path):
            return
        try:
            with open(trace_path, "r") as f:
                trace_data = f.read()
            # Parse pretty-printed JSON entries (separated by blank lines)
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
            # Store raw trace text
            game_ref.collection("trace").document("raw").set({"data": trace_data})
            print(f"[Bridge] Pushed trace for {game_id} ({len(trace_events)} events)")
        except Exception as e:
            print(f"[Bridge] Trace push failed: {e}")

    def _compute_stats(self) -> dict:
        """Compute aggregated stats from all games."""
        return compute_stats(self.games, self.session_id)


def compute_stats(games: list[dict], session_id: str = "") -> dict:
    """Compute aggregated stats from a list of game recaps (module-level, reusable)."""
    by_winner = {"crewmates": 0, "imposters": 0, "timeout": 0, "token_limit": 0}
    total_kills = 0
    total_ejections = 0
    player_stats: dict[str, dict] = {}

    for g in games:
        w = g.get("winner", "unknown")
        if w in by_winner:
            by_winner[w] += 1
        total_kills += g.get("kills", 0)
        total_ejections += g.get("ejections", 0)

        for p in g.get("players", []):
            name = p.get("name", "unknown")
            if name not in player_stats:
                player_stats[name] = {
                    "name": name,
                    "games": 0, "wins": 0,
                    "times_imposter": 0, "kills": 0,
                    "color": p.get("color"),
                }
            ps = player_stats[name]
            ps["games"] += 1
            if p.get("imposter"):
                ps["times_imposter"] += 1
            ps["kills"] += p.get("kills", 0)
            won = ((p.get("imposter") and w == "imposters") or
                   (not p.get("imposter") and w == "crewmates"))
            if won:
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
