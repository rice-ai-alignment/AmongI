"""experiment_config.py — Tree-structured experiment configuration.

Loaded from a JSON file, the config tree defines every swappable component.
Each node has a 'type' and optional 'params' that may themselves be nodes.

Example config.json:
{
  "type": "experiment",
  "params": {
    "map":      { "type": "SquareMap",   "params": { "size": 20 } },
    "agents":   { "type": "AgentGroup",  "params": { "count": 5 } },
    "engine":   { "type": "GameEngine",  "params": { "tick_interval": 3.0 } }
  }
}
"""

from __future__ import annotations

import json
from typing import Any, Optional


class ConfigNode:
    """One node in the experiment config tree. Has a type name, optional
    string id, and a dict of params (which may contain nested ConfigNodes)."""

    def __init__(self, ctype: str, cid: str = "", params: dict[str, Any] | None = None):
        self.ctype = ctype          # e.g. "SquareMap", "AgentGroup"
        self.cid = cid              # optional identifier for referencing
        self.params = params or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def get_node(self, key: str) -> Optional[ConfigNode]:
        v = self.params.get(key)
        return v if isinstance(v, ConfigNode) else None

    def __repr__(self):
        return f"ConfigNode({self.ctype}, id={self.cid!r}, params={list(self.params)})"


class ExperimentConfig:
    """Top-level experiment configuration loaded from a JSON file."""

    def __init__(self, path: str):
        with open(path, "r") as f:
            raw = json.load(f)
        self.root = self._parse(raw)
        print(f"[Config] Loaded experiment from {path}")

    def _parse(self, obj: Any) -> Any:
        """Recursively parse a JSON object into ConfigNodes."""
        if isinstance(obj, dict):
            if "type" in obj:
                params = {}
                for k, v in obj.items():
                    if k == "type":
                        continue
                    params[k] = self._parse(v)
                return ConfigNode(obj["type"], params=params)
            else:
                return {k: self._parse(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._parse(item) for item in obj]
        else:
            return obj

    def build_map(self, node: ConfigNode = None) -> Any:
        """Build a map from its config node."""
        from components.map_data import FileMap, SquareMap, CircleMap
        if node is None:
            node = self.root.get_node("map")
        if node is None:
            return SquareMap(16)
        registry = {
            "FileMap": lambda n: FileMap(n.get("path", "map_data.json")),
            "SquareMap": lambda n: SquareMap(n.get("size", 16)),
            "CircleMap": lambda n: CircleMap(n.get("diameter", 16)),
        }
        builder = registry.get(node.ctype)
        if builder:
            return builder(node)
        print(f"[Config] Unknown map type '{node.ctype}' — using SquareMap(16)")
        return SquareMap(16)

    def get_engine_params(self) -> dict:
        """Return flat dict of engine parameters."""
        eng = self.root.get_node("engine")
        if eng is None:
            return {}
        return {
            "agent_count": eng.get("agent_count", 5),
            "tick_interval": eng.get("tick_interval", 3.0),
            "kill_distance": eng.get("kill_distance", 3),
            "visibility_radius": eng.get("visibility_radius", 5),
            "witness_distance": eng.get("witness_distance", 5),
            "vote_timeout": eng.get("vote_timeout", 30.0),
            "min_vote_time": eng.get("min_vote_time", 15.0),
            "imposter_count": eng.get("imposter_count", 1),
        }
