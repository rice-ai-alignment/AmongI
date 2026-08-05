#!/usr/bin/env python3
"""run.py - One-command launcher for the Among-I engine + Firestore bridge.

Usage:
    python run.py                          # headless engine + bridge
    python run.py --render                 # with Godot renderer
    python run.py --agent-count 7          # 7 players
    python run.py --firebase               # push game data to Firestore
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_server import LogStore, init_firestore


async def _tail_loop(store: LogStore, interval: float):
    """Background task: tail log files and push to Firestore."""
    while True:
        store.tail()
        await asyncio.sleep(interval)


async def main():
    parser = argparse.ArgumentParser(description="Among-I — engine + bridge")
    parser.add_argument("--render", action="store_true",
                        help="Connect to Godot renderer on :8081")
    parser.add_argument("--render-host", default="localhost")
    parser.add_argument("--render-port", type=int, default=8081)
    parser.add_argument("--agent-count", type=int, default=5)
    parser.add_argument("--map", default=None, help="Path to map JSON (default: built-in)")
    parser.add_argument("--log-dir", default="../log")
    parser.add_argument("--firebase", action="store_true",
                        help="Push game data to Firestore")
    parser.add_argument("--study", default="", help="Firestore study name")
    parser.add_argument("--experiment", default="", help="Firestore experiment name")
    args = parser.parse_args()

    # Pass study/experiment to bridge via env
    if args.study:
        os.environ["STUDY_ID"] = args.study
    if args.experiment:
        os.environ["EXPERIMENT_CODE"] = args.experiment

    base = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.abspath(os.path.join(base, args.log_dir))

    # ── Bridge (log tailer → Firestore) ──────────────────────────────────
    store = LogStore(log_dir)
    store.load_logs()
    if args.firebase:
        init_firestore()

    tail_task = asyncio.create_task(_tail_loop(store, interval=5.0))

    # ── Engine ──────────────────────────────────────────────────────────
    from engine import GameEngine, GameConfig, MapData, EventStore
    from render_client import RenderClient

    config = GameConfig()
    config.player_count = args.agent_count

    map_path = os.path.join(base, args.map) if args.map else None
    map_data = MapData(map_path)
    event_store = EventStore(log_dir=log_dir)
    print(f"[run] Logs: {log_dir}")

    render_client = None
    if args.render:
        render_client = RenderClient(args.render_host, args.render_port)

    engine = GameEngine(config, map_data, event_store, render_client, [])

    try:
        await engine.run()
    except KeyboardInterrupt:
        print("\n[run] Shutting down...")
    finally:
        tail_task.cancel()
        print("[run] Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
