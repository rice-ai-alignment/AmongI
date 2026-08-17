"""render_client.py — WebSocket client that sends render events to Godot.

Connects to the Godot render server on port 8081. Handles reconnection
and provides a simple send_event() interface for the game engine.
"""

from __future__ import annotations
import asyncio
import json
import time
from typing import Optional

class RenderClient:
    """WebSocket client that pushes render events to Godot on port 8081."""

    def __init__(self, host: str = "localhost", port: int = 8081,
                 reconnect_delay: float = 2.0, heartbeat_interval: float = 5.0):
        self.uri = f"ws://{host}:{port}"
        self._ws: Optional[any] = None
        self._reconnect_delay = reconnect_delay
        self._heartbeat_interval = heartbeat_interval
        self._tick = 0
        self._last_send_time = 0.0
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Connect to Godot render server. Returns True on success."""
        try:
            import websockets
            self._ws = await websockets.connect(
                self.uri,
                open_timeout=5.0,
                close_timeout=2.0,
            )
            self._connected = True
            self._last_send_time = time.time()
            print(f"[RenderClient] Connected to Godot render server at {self.uri}")
            return True
        except Exception as e:
            self._connected = False
            print(f"[RenderClient] Could not connect to Godot at {self.uri}: {e}")
            return False

    async def send_event(self, event: dict) -> bool:
        """Send a single render event to Godot. Returns True on success."""
        if not self._ws or not self._connected:
            return False
        try:
            payload = json.dumps(event)
            await self._ws.send(payload)
            self._last_send_time = time.time()
            return True
        except Exception as e:
            print(f"[RenderClient] Send failed: {e}")
            self._connected = False
            return False

    async def send_batch(self, events: list[dict]) -> int:
        """Send multiple events. Returns count of successfully sent events."""
        sent = 0
        for ev in events:
            if await self.send_event(ev):
                sent += 1
        return sent

    async def send_heartbeat(self) -> bool:
        """Send a heartbeat event (if it's been long enough since last send)."""
        now = time.time()
        if now - self._last_send_time >= self._heartbeat_interval:
            self._tick += 1
            return await self.send_event({
                "type": "heartbeat", "tick": self._tick, "timestamp": now})
        return True  # Not time yet, but not an error

    async def send_full_state(self, events: list[dict]) -> bool:
        """Send a complete state snapshot (used after reconnection)."""
        print(f"[RenderClient] Sending full state ({len(events)} events)...")
        for ev in events:
            if not await self.send_event(ev):
                return False
        return True

    async def flush(self):
        """Ensure all sent events have reached Godot before closing.

        A ping round-trip guarantees everything queued on the socket has
        been delivered — closing immediately after send() would discard
        buffered events (e.g. the final game_end)."""
        if not self._ws or not self._connected:
            return
        try:
            await asyncio.wait_for(self._ws.ping(), timeout=3.0)
        except Exception:
            # Older websockets or already-closing socket — best effort
            await asyncio.sleep(0.3)

    async def close(self):
        """Close the WebSocket connection."""
        self._connected = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        print("[RenderClient] Disconnected from Godot")

    async def reconnect_loop(self):
        """Keep trying to connect/reconnect until successful (exponential backoff)."""
        delay = 1.0
        while not self._connected:
            if await self.connect():
                return
            print(f"[RenderClient] Retrying in {delay:.0f}s...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)  # exponential backoff, max 30s
