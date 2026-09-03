#!/usr/bin/env python3
"""validate_configs.py — Run the shared JS config compiler from Python.

The compiler lives in schema_compiler.js (single source of truth —
also used by the website). This script exports the schema from the
Python component registry, then shells out to Node to validate configs.

Usage:
    python validate_configs.py [path ...]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
DASHBOARD_PUBLIC = BASE.parent / "dashboard" / "public"
EXAMPLES_DIR = BASE / "examples"
SKIP = {"sample_games.json", "firebase-key.json", "map_data.json",
        "version.json", "experiment.json"}  # non-config / legacy


def export_schema() -> Path:
    """Regenerate schema.json from the Python registry (source of truth
    for component definitions)."""
    sys.path.insert(0, str(BASE))
    from experiment import export_schema
    out = DASHBOARD_PUBLIC / "schema.json"
    export_schema(str(out))
    return out


def main():
    schema_path = export_schema()

    if not shutil.which("node"):
        print("[validate_configs] ERROR: node not found — cannot run compiler")
        return 2

    args = sys.argv[1:]
    if args:
        configs = args
    else:
        configs = [str(p) for p in sorted(BASE.glob("*.json")) if p.name not in SKIP]
        # Example configs — engine/examples/ is the single source of truth
        # (synced into dashboard/public/sample_data at build time).
        configs += [str(p) for p in sorted(EXAMPLES_DIR.rglob("*.json"))]

    cmd = ["node", str(BASE / "validate.js"), "--schema", str(schema_path)] + configs
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
