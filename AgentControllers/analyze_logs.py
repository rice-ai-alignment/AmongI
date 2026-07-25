#!/usr/bin/env python3
"""Analyze Among-I event logs (JSONL format from EventLogger autoload).

Usage:
    python analyze_logs.py [--dir PATH] [--session ID] [--recent N] [--latest]

Examples:
    python analyze_logs.py --dir ../among-i --latest        # show newest session
    python analyze_logs.py --dir ../among-i --recent 5      # last 5 sessions summary
    python analyze_logs.py --dir ../among-i --session 2026-07-04  # drill into session
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def analyze_event_log(filepath: Path) -> dict:
    events = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not events:
        return {"file": filepath.name, "events": [], "empty": True}

    categories = Counter(e.get("category", "?") for e in events)
    types = Counter(e.get("type", "?") for e in events)
    kills = sum(1 for e in events if e.get("type") == "kill")
    ejections = sum(1 for e in events if e.get("type") == "eject")
    votes = [e for e in events if e.get("category") == "voting"]
    duration_s = events[-1].get("elapsed_ms", 0) / 1000.0 if events else None

    return {
        "file": filepath.name,
        "events": events,
        "categories": dict(categories.most_common()),
        "types": dict(types.most_common()),
        "kills": kills,
        "ejections": ejections,
        "votes": votes,
        "duration_s": duration_s,
        "empty": False,
    }


def print_session_detail(sid: str, data: dict):
    ev = data.get("event", {})
    if ev.get("empty"):
        print(f"Session {sid}: no events.")
        return

    print(f"\n{'=' * 80}")
    print(f"  Session: {sid}")
    print(f"  File: {ev['file']}")
    print(f"  Events: {len(ev['events'])}  |  Kills: {ev['kills']}  |  "
          f"Ejections: {ev['ejections']}  |  "
          f"Duration: {ev['duration_s']:.0f}s" if ev.get("duration_s") else "?")
    print(f"{'=' * 80}")

    for e in ev["events"]:
        ts = e.get("elapsed_ms", 0) / 1000.0
        cat = e.get("category", "?")
        typ = e.get("type", "?")
        # Show meaningful details without clutter
        skip = {"id", "session", "timestamp", "elapsed_ms", "category",
                "type", "map", "version", "event_count"}
        details = {k: v for k, v in e.items() if k not in skip}
        detail_str = "  ".join(f"{k}={v}" for k, v in details.items())
        print(f"  [{ts:8.1f}s] {cat:8s}/{typ:16s}  {detail_str}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Among-I event logs")
    parser.add_argument("--dir", default=None, help="Path to among-i/ project root")
    parser.add_argument("--session", default=None, help="Filter by session ID substring")
    parser.add_argument("--recent", type=int, default=0, help="Show last N sessions")
    parser.add_argument("--latest", action="store_true", help="Show the most recently created log in detail")
    args = parser.parse_args()

    if args.dir:
        base = Path(args.dir)
    else:
        candidates = [
            Path.cwd(),
            Path.cwd() / "among-i",
            Path(__file__).resolve().parent.parent / "among-i",
        ]
        base = next((c for c in candidates if (c / "logs").exists()), None)
        if base is None:
            print("ERROR: Cannot find among-i/ directory. Use --dir to specify.")
            sys.exit(1)

    event_dir = base / "logs"

    sessions = {}
    for ef in sorted(event_dir.glob("SESSION-*.jsonl")):
        if ef.stat().st_size == 0:
            continue
        sid = ef.stem
        sessions[sid] = {"event": analyze_event_log(ef)}

    if args.session:
        sessions = {k: v for k, v in sessions.items() if args.session in k}
        if not sessions:
            print(f"No sessions matching '{args.session}'")
            sys.exit(1)

    session_items = sorted(sessions.items())
    if args.recent > 0:
        session_items = session_items[-args.recent:]

    # ── Latest mode: pick newest file by mtime ────────────────────
    if args.latest:
        newest = None
        newest_mtime = 0
        for ef in event_dir.glob("SESSION-*.jsonl"):
            if ef.stat().st_size == 0:
                continue
            mtime = ef.stat().st_mtime
            if mtime > newest_mtime:
                newest_mtime = mtime
                newest = ef
        if newest is None:
            print("No non-empty log files found.")
            sys.exit(1)
        sid = newest.stem
        data = {"event": analyze_event_log(newest)}
        print_session_detail(sid, data)
        return

    # ── Detail mode ──────────────────────────────────────────────
    if args.session and len(sessions) <= 3:
        for sid, data in session_items:
            print_session_detail(sid, data)
        return

    # ── Summary mode ─────────────────────────────────────────────
    print("=" * 75)
    print("  Among-I Event Log Analysis")
    print(f"  Source: {event_dir}")
    print("=" * 75)

    total_events = 0
    total_kills = 0
    total_ejections = 0
    total_votes = 0
    category_totals = Counter()
    nonempty = 0

    for sid, data in session_items:
        ev = data.get("event", {})
        if ev.get("empty"):
            continue
        nonempty += 1
        total_events += len(ev["events"])
        total_kills += ev["kills"]
        total_ejections += ev["ejections"]
        total_votes += len(ev["votes"])
        for cat, count in ev["categories"].items():
            category_totals[cat] += count

    print(f"\n  Sessions: {nonempty} (of {len(session_items)} total)")
    print(f"  Total events: {total_events}")
    print(f"  Event categories: {dict(category_totals.most_common())}")
    print(f"  Kills: {total_kills}  |  Ejections: {total_ejections}  |  Votes cast: {total_votes}")
    print()

    # Session table
    print(f"{'─' * 90}")
    print(f"  {'Session':<40s} {'Events':>7s} {'Kills':>6s} {'Eject':>6s} {'Votes':>6s} {'Duration':>10s}")
    print(f"  {'-' * 88}")
    for sid, data in session_items[-25:]:
        ev = data.get("event", {})
        if ev.get("empty"):
            continue
        dur = ev.get("duration_s")
        dur_str = f"{dur:.0f}s" if dur else "?"
        display = sid[:38] if len(sid) > 38 else sid
        print(f"  {display:<40s} {len(ev['events']):>7d} {ev['kills']:>6d} "
              f"{ev['ejections']:>6d} {len(ev['votes']):>6d} {dur_str:>10s}")

    print(f"\n{'=' * 75}")
    print("  Commands:")
    print("    --session <id>    Drill into a specific session (all events)")
    print("    --recent N        Show only last N sessions")
    print(f"  Open LogAnalysis/viewer.html for visual event timeline.")
    print("=" * 75)


if __name__ == "__main__":
    main()
