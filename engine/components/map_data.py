"""map_data.py — Pluggable tile-map sources.

BaseMap is the abstract interface. Implementations:
  - FileMap      — loads from a JSON file
  - SquareMap    — auto-generated open square with border walls
  - CircleMap    — auto-generated circular arena
"""

from __future__ import annotations

import json
import math
import os
import random
from abc import ABC, abstractmethod

from position import Tile


class BaseMap(ABC):
    """Abstract walkable-grid map. Subclasses provide the tile set."""

    def __init__(self):
        self.width: int = 0
        self.height: int = 0
        self.min_x: int = 0
        self.max_x: int = 0
        self.min_y: int = 0
        self.max_y: int = 0
        self._walkable: set[Tile] = set()

    def is_walkable(self, x: int, y: int) -> bool:
        return Tile(x, y) in self._walkable

    def random_tile(self) -> Tile:
        t = random.choice(list(self._walkable)) if self._walkable else Tile(0, 0)
        return Tile(t.x, t.y)

    random_walkable_tile = random_tile  # alias for backward compat

    def distance(self, a: Tile, b: Tile) -> float:
        return a.distance_to(b)

    def serialize(self) -> dict:
        """JSON-serialisable map representation for log / Godot."""
        return {
            "width": self.width, "height": self.height,
            "min_x": self.min_x, "max_x": self.max_x,
            "min_y": self.min_y, "max_y": self.max_y,
            "walkable": [[t.x, t.y] for t in self._walkable],
        }


# ── File-backed map ──────────────────────────────────────────────────────

class FileMap(BaseMap):
    """Load walkable tiles from a JSON file (format: {width, height, walkable: [[x,y],...]})."""

    def __init__(self, path: str):
        super().__init__()
        with open(path, "r") as f:
            data = json.load(f)
        self._init_from_data(data)
        print(f"[Map] Loaded {path} ({self.width}x{self.height}, "
              f"{len(self._walkable)} walkable)")

    def _init_from_data(self, data: dict):
        self.width = data["width"]
        self.height = data["height"]
        self.min_x = data.get("min_x", 0)
        self.max_x = data.get("max_x", self.min_x + self.width - 1)
        self.min_y = data.get("min_y", 0)
        self.max_y = data.get("max_y", self.min_y + self.height - 1)
        self._walkable = set()
        for coord in data.get("walkable", []):
            self._walkable.add(Tile(coord[0], coord[1]))


# ── Generated maps ───────────────────────────────────────────────────────

class SquareMap(BaseMap):
    """A square arena — open interior with a 1-tile border wall."""

    def __init__(self, size: int = 16, wall: int = 1):
        super().__init__()
        self.width = size
        self.height = size
        self.min_x = 0
        self.max_x = size - 1
        self.min_y = 0
        self.max_y = size - 1
        for x in range(wall, size - wall):
            for y in range(wall, size - wall):
                self._walkable.add(Tile(x, y))
        print(f"[Map] Square arena {size}x{size} "
              f"({len(self._walkable)} walkable)")


class CircleMap(BaseMap):
    """A circular arena — tiles within `radius` of the centre are walkable."""

    def __init__(self, diameter: int = 16):
        super().__init__()
        self.width = diameter
        self.height = diameter
        self.min_x = 0
        self.max_x = diameter - 1
        self.min_y = 0
        self.max_y = diameter - 1
        cx = (diameter - 1) / 2.0
        cy = (diameter - 1) / 2.0
        r = diameter / 2.0 - 0.5
        for x in range(diameter):
            for y in range(diameter):
                if math.sqrt((x - cx) ** 2 + (y - cy) ** 2) <= r:
                    self._walkable.add(Tile(x, y))
        print(f"[Map] Circle arena {diameter}x{diameter} "
              f"({len(self._walkable)} walkable)")
