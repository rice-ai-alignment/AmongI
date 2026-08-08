"""render_relay.py — WebSocket broadcast hub for remote Godot viewing.

Replaces Godot's Server.gd role on a server machine: the local engine's
RenderClient connects as a normal client; remote Godot viewers connect
as additional clients. Every received message is broadcast to all other
clients. A replay buffer lets late-joining viewers catch up.

Usage:
    python render_relay.py [--host 0.0.0.0] [--port 8081] [--buffer 200]
"""

from __future__ import annotations

import asyncio


class RenderRelay:
    """WebSocket broadcast hub for render events."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8081,
                 replay_buffer_size: int = 200):
        self.host = host
        self.port = port
        self._replay_buffer: list[str] = []
        self._replay_max = replay_buffer_size
        self._clients: set = set()
        self._server = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def _add_to_buffer(self, message: str):
        self._replay_buffer.append(message)
        if len(self._replay_buffer) > self._replay_max:
            self._replay_buffer = self._replay_buffer[-self._replay_max:]

    async def start(self):
        """Start the relay server. Blocks until stop() is called."""
        import websockets
        async with websockets.serve(self._handler, self.host, self.port):
            print(f"[RenderRelay] Listening on {self.host}:{self.port}")
            await asyncio.get_running_loop().create_future()  # run forever

    async def _handler(self, websocket):
        """Handle one client connection."""
        self._clients.add(websocket)
        print(f"[RenderRelay] Client connected ({len(self._clients)} total)")
        try:
            # Replay buffer for late joiners — send full state catch-up
            if self._replay_buffer:
                for msg in self._replay_buffer:
                    try:
                        await websocket.send(msg)
                    except Exception:
                        # Client disconnected during replay — clean up
                        self._clients.discard(websocket)
                        return
                print(f"[RenderRelay] Replayed {len(self._replay_buffer)} events to late joiner")

            async for message in websocket:
                # Broadcast to all OTHER clients
                self._add_to_buffer(message)
                dead = set()
                for client in self._clients:
                    if client is websocket:
                        continue
                    try:
                        await client.send(message)
                    except Exception:
                        dead.add(client)
                self._clients -= dead
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            print(f"[RenderRelay] Client disconnected ({len(self._clients)} total)")


# ── CLI ─────────────────────────────────────────────────────────────────────

async def main():
    import argparse
    p = argparse.ArgumentParser(description="Render event relay for remote Godot")
    p.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    p.add_argument("--port", type=int, default=8081, help="Port (default: 8081)")
    p.add_argument("--buffer", type=int, default=200,
                   help="Replay buffer size for late joiners (default: 200)")
    args = p.parse_args()

    import websockets
    relay = RenderRelay(args.host, args.port, args.buffer)
    async with websockets.serve(relay._handler, relay.host, relay.port):
        print(f"[RenderRelay] Listening on {relay.host}:{relay.port} "
              f"(buffer={relay._replay_max})")
        await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
