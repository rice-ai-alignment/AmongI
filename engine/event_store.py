"""event_store.py — JSONL event logging for the Among-I Python engine.

Replaces EventLogger.gd. Writes structured JSON events to both a
session-level log file and per-game log files, matching the format
expected by the web log viewer (server.mjs + public/index.html).
"""

from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional


class EventStore:
    """Writes structured JSONL event logs for a session and its games.

    Mirrors the log structure produced by EventLogger.gd:
      - Session log:  logs/SESSION-<ts>.jsonl
      - Per-game log: logs/SESSION-<ts>/GAME-NNN.jsonl

    Each event is a single JSON object written as one line (JSONL).
    Events are buffered and flushed periodically or at a batch threshold.
    """

    def __init__(self, log_dir: str = "logs",
                 flush_interval_sec: float = 5.0,
                 flush_batch_size: int = 20):
        self._log_dir = log_dir
        self._flush_interval = flush_interval_sec
        self._flush_batch_size = flush_batch_size

        # Session state
        self._session_id: str = ""
        self._session_start: float = 0.0
        self._session_file: Optional[object] = None
        self._session_path: str = ""
        self._event_count: int = 0

        # Game state
        self._game_id: str = ""
        self._game_count: int = 0
        self._game_file: Optional[object] = None
        self._game_path: str = ""
        self._game_event_count: int = 0
        self._game_start: float = 0.0

        # Buffer
        self._buffer: list[dict] = []
        self._last_flush: float = 0.0

    # ── Session lifecycle ────────────────────────────────────────────

    def start_session(self) -> str:
        """Open a new session log. Returns the session ID."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        self._session_id = f"SESSION-{ts}"
        self._session_start = time.time()
        self._event_count = 0
        self._last_flush = time.time()

        os.makedirs(self._log_dir, exist_ok=True)
        self._session_path = os.path.join(self._log_dir, f"{self._session_id}.jsonl")
        self._session_file = open(self._session_path, "w", encoding="utf-8")

        self._log_event_raw("system", "session_start", {
            "session_id": self._session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._flush()
        print(f"[EventStore] Session started: {self._session_path}")
        return self._session_id

    def end_session(self):
        """Close the session log."""
        if self._game_file:
            self.end_game({})  # Finalize any open game

        self._log_event_raw("system", "session_end", {
            "total_events": self._event_count,
            "total_games": self._game_count,
        })
        self._flush()
        if self._session_file:
            self._session_file.close()
            self._session_file = None
        print(f"[EventStore] Session ended: {self._session_id} "
              f"({self._event_count} events, {self._game_count} games)")

    # ── Game lifecycle ───────────────────────────────────────────────

    def start_game(self) -> str:
        """Open a new per-game log. Returns the game ID."""
        self._game_count += 1
        self._game_id = f"GAME-{self._game_count:03d}"
        self._game_event_count = 0
        self._game_start = time.time()

        # Ensure game log directory exists
        game_dir = os.path.join(self._log_dir, self._session_id)
        os.makedirs(game_dir, exist_ok=True)
        self._game_path = os.path.join(game_dir, f"{self._game_id}.jsonl")
        self._game_file = open(self._game_path, "w", encoding="utf-8")

        self.log_event("system", "game_start", {"game_id": self._game_id})
        print(f"[EventStore] Game started: {self._game_id} -> {self._game_path}")
        return self._game_id

    def end_game(self, recap: dict):
        """Close the per-game log with a final recap event."""
        if not self._game_file:
            return

        self.log_event("system", "game_end", {
            "game_id": self._game_id,
            "recap": recap,
        })
        self._flush()  # Force flush for game end

        self._game_file.close()
        self._game_file = None
        print(f"[EventStore] Game ended: {self._game_id} "
              f"({self._game_event_count} events)")

    # ── Event logging ────────────────────────────────────────────────

    def log_event(self, category: str, event_type: str,
                  data: Optional[dict] = None) -> dict:
        """Log a structured event. Returns the event dict (with generated id)."""
        return self._log_event_raw(category, event_type, data or {})

    def _log_event_raw(self, category: str, event_type: str,
                       data: dict) -> dict:
        """Internal: build and buffer an event."""
        elapsed_ms = int((time.time() - self._session_start) * 1000)

        event = {
            "id": f"{self._event_count:06d}",
            "session": self._session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": elapsed_ms,
            "category": category,
            "type": event_type,
            **data,
        }

        if self._game_id:
            event["game_id"] = self._game_id
            event["game_event_id"] = self._game_event_count
            self._game_event_count += 1

        self._event_count += 1

        # Write to session log buffer
        self._buffer.append(event)

        # Write and flush immediately to per-game log (if open)
        if self._game_file:
            self._game_file.write(json.dumps(event) + "\n")
            self._game_file.flush()

        # Auto-flush if buffer is large enough
        if len(self._buffer) >= self._flush_batch_size:
            self._flush()

        return event

    def _flush(self):
        """Write buffered events to the session log file."""
        if not self._buffer or not self._session_file:
            return

        for ev in self._buffer:
            self._session_file.write(json.dumps(ev) + "\n")
        self._session_file.flush()
        self._buffer.clear()
        self._last_flush = time.time()

    def tick(self):
        """Call periodically — flushes if the interval has elapsed."""
        if time.time() - self._last_flush >= self._flush_interval:
            self._flush()

    # ── Accessors ────────────────────────────────────────────────────

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def game_id(self) -> str:
        return self._game_id

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def log_dir(self) -> str:
        return self._log_dir
