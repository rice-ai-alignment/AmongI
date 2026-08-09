"""event_manager.py — Centralised event emission, logging, and tracing.

Wraps :class:`EventStore` (JSONL) and :class:`RenderClient` (Godot)
so the engine delegates all output through a single component.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from experiment import ExperimentComponent, Param


class EventManager(ExperimentComponent):
    """Handles event logging, render emission, and trace output.

    The engine calls :meth:`emit` for every game event.  This method
    writes to the JSONL log and pushes to the Godot renderer in one call.
    Trace entries (LLM prompts, decisions) go through :meth:`trace`.
    """

    component_type = "EventManager"
    params = {}

    def __init__(self, event_store=None, render_client=None, **kwargs):
        super().__init__(**kwargs)
        self._store = event_store
        self._render = render_client
        self._trace_files: list = []   # open file handles for trace output
        self._tick: int = 0

    # ── wiring ──────────────────────────────────────────────────────────

    def attach(self, event_store, render_client=None):
        self._store = event_store
        self._render = render_client

    @property
    def store(self):
        return self._store

    @property
    def render(self):
        return self._render

    # ── event emission ──────────────────────────────────────────────────

    async def emit(self, category: str, event_type: str, data: dict) -> dict:
        """Log the event and push to the render client.  Returns the full
        event dict (including envelope fields added by the store)."""
        event = {}
        if self._store:
            event = self._store.log_event(category, event_type, data)
        if self._render:
            await self._render.send_event(
                event if event else {"type": event_type, **data})
        return event

    # ── trace ───────────────────────────────────────────────────────────

    def open_trace(self, path: str):
        """Open a trace file for structured debug output."""
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        f = open(path, "w", encoding="utf-8")
        self._trace_files.append(f)

    def trace(self, category: str, data: dict):
        """Write a trace entry to all open trace files."""
        entry = {
            "timestamp": time.time(),
            "tick": self._tick,
            "category": category,
            **data,
        }
        line = json.dumps(entry, indent=2) + "\n\n"
        for f in self._trace_files:
            try:
                f.write(line)
                f.flush()
            except Exception:
                pass

    def close_traces(self):
        for f in self._trace_files:
            try:
                f.close()
            except Exception:
                pass
        self._trace_files.clear()

    # ── lifecycle ───────────────────────────────────────────────────────

    def start_session(self, session_id: str = ""):
        if self._store:
            self._store.start_session(session_id)

    def end_session(self, total_games: int = 0):
        if self._store:
            self._store.end_session(total_games)
        self.close_traces()

    def start_game(self, game_id: str):
        if self._store:
            self._store.start_game(game_id)

    def end_game(self, recap: dict):
        if self._store:
            self._store.end_game(recap)

    def description(self) -> str:
        return "event manager"
