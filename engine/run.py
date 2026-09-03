#!/usr/bin/env python3
"""run.py - One-command launcher for the Among-I engine + Firestore bridge.

Usage:
    python run.py --config experiment.json              # headless
    python run.py --config experiment.json --render     # with Godot
    python run.py --config experiment.json --firebase   # push to Firestore
    python run.py --config-firestore --study S --exp E --firebase  # config from Firestore
    python run.py --list-examples                      # list example configs
    python run.py --example                            # interactive example picker
    python run.py --example among_us/example_basic     # pick by path (or index)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_server import LogStore, init_firestore, check_study_experiment


# ── Example config picker ────────────────────────────────────────────────
# Examples live in engine/examples/ (single source of truth — the
# dashboard syncs them into public/sample_data/ at build time).

def list_examples(base_dir: str) -> list[str]:
    """All example configs under base_dir as relative paths, sorted."""
    out = []
    for root, _dirs, files in os.walk(base_dir):
        for f in sorted(files):
            if f.endswith(".json"):
                out.append(os.path.relpath(os.path.join(root, f), base_dir))
    return out


def resolve_example(base_dir: str, name: str, examples: list[str]):
    """Resolve --example NAME to a relative path, or None.

    NAME may be an empty string (interactive picker), a 1-based index,
    a relative path, or a (unique) bare filename.
    """
    if name == "":
        print("[run] example configs:")
        for i, p in enumerate(examples, 1):
            print(f"  {i:>3}) {p}")
        raw = input("pick an example (number or path): ").strip()
        if not raw:
            print("[run] cancelled.")
            return None
        name = raw

    if name.isdigit():
        idx = int(name) - 1
        if 0 <= idx < len(examples):
            return examples[idx]
        print(f"[run] no example #{name} (1-{len(examples)})")
        return None

    # Normalize: names may be given with or without the .json extension.
    key = name if name.endswith(".json") else name + ".json"
    stem = os.path.splitext(name)[0]

    # Exact relative path, then path suffix, then unique bare filename
    exact = [p for p in examples if p == key]
    if len(exact) == 1:
        return exact[0]
    suff = [p for p in examples if p.endswith("/" + key) or p.endswith("/" + name)]
    if len(suff) == 1:
        return suff[0]
    base_matches = [p for p in examples
                    if os.path.splitext(os.path.basename(p))[0] == stem]
    if len(base_matches) == 1:
        return base_matches[0]
    matches = exact or suff or base_matches
    if matches:
        print(f"[run] ambiguous example '{name}' — matches: {', '.join(matches)}")
    else:
        print(f"[run] no example matches '{name}' — try --list-examples")
    return None


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
    parser.add_argument("--config", default=None, help="Path to experiment JSON config")
    parser.add_argument("--config-firestore", action="store_true",
                        help="Load experiment config from Firestore (requires --study --experiment)")
    parser.add_argument("--example", nargs="?", const="", default=None, metavar="NAME",
                        help="Pick an example config from engine/examples/ "
                             "(NAME = path, index, or empty for an interactive picker)")
    parser.add_argument("--list-examples", action="store_true",
                        help="List example configs in engine/examples/ and exit")
    parser.add_argument("--map", default=None, help="Path to map JSON (overrides config)")
    parser.add_argument("--log-dir", default="../log")
    parser.add_argument("--firebase", action="store_true",
                        help="Push game data to Firestore")
    parser.add_argument("--study", default="", help="Firestore study name")
    parser.add_argument("--experiment", default="", help="Firestore experiment name")
    parser.add_argument("--max-games", type=int, default=None,
                        help="Stop after N games (default: run forever)")
    args = parser.parse_args()

    # Pass study/experiment to bridge via env
    if args.study:
        os.environ["STUDY_ID"] = args.study
    if args.experiment:
        os.environ["EXPERIMENT_CODE"] = args.experiment

    base = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.abspath(os.path.join(base, args.log_dir))

    # ── Example picker ───────────────────────────────────────────────────
    examples_dir = os.path.join(base, "examples")
    examples = list_examples(examples_dir)
    if args.list_examples:
        print("[run] example configs:")
        for i, p in enumerate(examples, 1):
            print(f"  {i:>3}) {p}")
        return
    if args.example is not None:
        if args.config or args.config_firestore:
            print("[run] --example cannot be combined with --config/--config-firestore")
            return
        picked = resolve_example(examples_dir, args.example, examples)
        if not picked:
            return
        args.config = os.path.join(examples_dir, picked)
        print(f"[run] Using example: {picked}")

    # ── Bridge (log tailer → Firestore) ──────────────────────────────────
    store = LogStore(log_dir)
    store.load_logs()
    if args.firebase:
        init_firestore()
        if args.study and args.experiment:
            if not check_study_experiment(args.study, args.experiment):
                print("[run] Aborting — study/experiment not found in Firestore")
                return

    tail_task = asyncio.create_task(_tail_loop(store, interval=5.0))

    # ── Engine ──────────────────────────────────────────────────────────
    from engine import GameEngine, GameConfig
    from components.maps import SquareMap, CircleMap, FileMap
    from event_store import EventStore
    from render_client import RenderClient
    from experiment_runtime import experiment_to_runtime

    # Load experiment config from file or Firestore
    exp = None
    if args.config_firestore:
        # Fetch config from Firestore experiment doc
        from bridge_server import _firestore_ready
        if not _firestore_ready:
            print("[run] Firestore not initialized — run --firebase first")
            return
        from experiment import build_experiment_from_dict
        try:
            from google.cloud import firestore
            db = firestore.client()
            from bridge_server import STUDIES_COLLECTION
            col = STUDIES_COLLECTION
            exp_ref = db.collection(col).document(args.study).collection("experiments").document(args.experiment)
            exp_doc = exp_ref.get()
            if not exp_doc.exists:
                print(f"[run] Experiment doc not found: {col}/{args.study}/experiments/{args.experiment}")
                return
            exp_data = exp_doc.to_dict()
            config_json = exp_data.get("config")
            if not config_json:
                print(f"[run] No 'config' field on experiment doc — has a run completed yet?")
                return
            exp = build_experiment_from_dict(config_json)
            print(f"[run] Loaded experiment config from Firestore: {args.study}/{args.experiment}")
        except Exception as e:
            print(f"[run] Failed to load config from Firestore: {e}")
            return
    elif args.config:
        from experiment import build_experiment
        exp = build_experiment(os.path.join(base, args.config))

    agent_types = []
    if exp:
        config, free_roam_phase, voting_phase, win_conditions, position_mode, map_data, agent_types = \
            experiment_to_runtime(exp)
    else:
        config = GameConfig()
        free_roam_phase = None
        voting_phase = None
        win_conditions = []
        position_mode = None
        map_data = SquareMap(16)

    # Override map with CLI flag
    if args.map:
        map_data = FileMap(path=os.path.join(base, args.map))

    event_store = EventStore(log_dir=log_dir)
    print(f"[run] Logs: {log_dir}")

    render_client = None
    if args.render:
        render_client = RenderClient(args.render_host, args.render_port)

    engine = GameEngine(config, map_data, event_store, render_client, [],
                        free_roam_phase=free_roam_phase,
                        voting_phase=voting_phase,
                        win_conditions=win_conditions,
                        position_mode=position_mode)
    if exp:
        engine._agent_types = agent_types
        engine._experiment_config = exp.to_json()
        engine.game = exp

    try:
        summary = await engine.run(max_games=args.max_games)
        if summary:
            import json
            print(f"[run] Summary: {json.dumps(summary, indent=2)}")
    except KeyboardInterrupt:
        print("\n[run] Shutting down...")
    finally:
        tail_task.cancel()
        print("[run] Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
