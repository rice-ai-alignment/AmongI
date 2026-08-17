"""version.py — Read version from version.json so servers can report it."""

import json
import os


def get_version() -> str:
    """Return the current version string (e.g. '1.0.0')."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data.get("version", "0.0.0")
    except (FileNotFoundError, json.JSONDecodeError):
        return "0.0.0"


def bump_version(patch: bool = True) -> str:
    """Increment the version and write it back. Patch bump by default."""
    v = get_version()
    parts = [int(x) for x in v.split(".")]
    if patch:
        parts[2] += 1
    else:
        parts[1] += 1
        parts[2] = 0
    new_v = ".".join(str(x) for x in parts)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
    with open(path, "w") as f:
        json.dump({"version": new_v}, f, indent=2)
        f.write("\n")
    return new_v
