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
            return db.collection(FIRESTORE_COLLECTION).document(study) \
                     .collection("experiments").document(exp)
        # Fallback: session-based temp name
        sid = self.session_id or "unknown"
        return db.collection(FIRESTORE_COLLECTION).document(sid.replace("SESSION-", "exp-"))

    def _push_game(self, recap: dict):
        if not _firestore_ready:
            return
        try:
            game_id = recap.get("game_id", "unknown")
            if game_id in self._pushed_game_ids:
                return
            doc_ref = self._experiment_doc_ref()
            doc_ref.collection("games").document(game_id).set(recap)

            stats = self._compute_stats()
            doc_ref.set(stats, merge=True)
            self._pushed_game_ids.add(game_id)
            print(f"[Bridge] Pushed {game_id} to {doc_ref.path} "
                  f"({stats['total_games']} games, {stats['total_kills']} kills)")
        except Exception as e:
            print(f"[Bridge] Firestore push failed: {e}")

    def _compute_stats(self) -> dict:
        """Compute aggregated stats from all games."""
        by_winner = {"crewmates": 0, "imposters": 0, "timeout": 0, "token_limit": 0}
        total_kills = 0
        total_ejections = 0
        player_stats: dict[str, dict] = {}

        for g in self.games:
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
            "total_games": len(self.games),
            "total_kills": total_kills,
            "total_ejections": total_ejections,
            "by_winner": by_winner,
            "players": sorted(player_stats.values(),
                              key=lambda p: (p["wins"] / max(p["games"], 1), p["games"]),
                              reverse=True),
            "session_id": self.session_id,
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
