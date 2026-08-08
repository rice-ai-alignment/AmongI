"""Map components — define the walkable arena.

Each map class is BOTH an ExperimentComponent (declarative config with params,
type/class, to_json, schema) AND a runtime map (is_walkable, distance,
random_tile, serialize).  No separate config-vs-runtime split.
"""

import json
import math
import random

from experiment import ExperimentComponent, Param
from position import Tile


class _MapBase(ExperimentComponent):
    """Shared runtime behaviour for all map types.  Not registered."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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

    random_walkable_tile = random_tile  # backward-compat alias

    def distance(self, a: Tile, b: Tile) -> float:
        return a.distance_to(b)

    def serialize(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "min_x": self.min_x, "max_x": self.max_x,
            "min_y": self.min_y, "max_y": self.max_y,
            "walkable": [[t.x, t.y] for t in self._walkable],
        }


# ── Concrete map types ────────────────────────────────────────────────────


class SquareMap(_MapBase):
    """A square arena — open interior with a 1-tile border wall."""
    component_type = "Map"
    params = {"size": Param(int, 16, "Side length of the square arena")}
    exposes = {
        "variables": {
            "size": "int — side length of the square arena",
        },
        "functions": {
            "is_walkable": {"args": ["x", "y"], "returns": "bool", "desc": "Check if a tile is walkable"},
            "distance": {"args": ["a", "b"], "returns": "float", "desc": "Euclidean distance between two tiles"},
            "random_tile": {"args": [], "returns": "Tile", "desc": "Return a random walkable tile"},
        },
    }

    def __init__(self, size: int = 16, wall: int = 1, **kwargs):
        # Set params BEFORE super().__init__ so _validate() sees them
        kwargs.setdefault("size", size)
        super().__init__(**kwargs)
        self.width = self.size
        self.height = self.size
        self.min_x = 0
        self.max_x = self.size - 1
        self.min_y = 0
        self.max_y = self.size - 1
        for x in range(wall, self.size - wall):
            for y in range(wall, self.size - wall):
                self._walkable.add(Tile(x, y))
        print(f"[Map] Square arena {self.size}x{self.size} "
              f"({len(self._walkable)} walkable)")

    def description(self): return f"square arena ({self.size}x{self.size})"


class CircleMap(_MapBase):
    """A circular arena — tiles within radius of centre are walkable."""
    component_type = "Map"
    params = {"diameter": Param(int, 16, "Diameter of the circular arena")}
    exposes = {
        "variables": {"diameter": "int — diameter of the circular arena"},
        "functions": {
            "is_walkable": {"args": ["x", "y"], "returns": "bool", "desc": "Check if a tile is walkable"},
            "distance": {"args": ["a", "b"], "returns": "float", "desc": "Euclidean distance between two tiles"},
        },
    }

    def __init__(self, diameter: int = 16, **kwargs):
        kwargs.setdefault("diameter", diameter)
        super().__init__(**kwargs)
        self.width = self.diameter
        self.height = self.diameter
        self.min_x = 0
        self.max_x = self.diameter - 1
        self.min_y = 0
        self.max_y = self.diameter - 1
        cx = (self.diameter - 1) / 2.0
        cy = (self.diameter - 1) / 2.0
        r = self.diameter / 2.0 - 0.5
        for x in range(self.diameter):
            for y in range(self.diameter):
                if math.sqrt((x - cx) ** 2 + (y - cy) ** 2) <= r:
                    self._walkable.add(Tile(x, y))
        print(f"[Map] Circle arena {self.diameter}x{self.diameter} "
              f"({len(self._walkable)} walkable)")

    def description(self): return f"circle arena (d={self.diameter})"


class FileMap(_MapBase):
    """Load walkable tiles from a JSON file."""
    component_type = "Map"
    params = {"path": Param(str, "map_data.json", "Path to JSON map file")}
    exposes = {
        "variables": {"path": "str — path to the map JSON file"},
        "functions": {
            "is_walkable": {"args": ["x", "y"], "returns": "bool", "desc": "Check if a tile is walkable"},
            "distance": {"args": ["a", "b"], "returns": "float", "desc": "Euclidean distance between two tiles"},
        },
    }

    def __init__(self, path: str = "map_data.json", **kwargs):
        kwargs.setdefault("path", path)
        super().__init__(**kwargs)
        with open(self.path, "r") as f:
            data = json.load(f)
        self._init_from_data(data)
        print(f"[Map] Loaded {self.path} ({self.width}x{self.height}, "
              f"{len(self._walkable)} walkable)")

    def _init_from_data(self, data: dict):
        self.width = data["width"]
        self.height = data["height"]
        self.min_x = data.get("min_x", 0)
        self.max_x = data.get("max_x", self.min_x + self.width - 1)
        self.min_y = data.get("min_y", 0)
        self.max_y = data.get("max_y", self.min_y + self.height - 1)
        for coord in data.get("walkable", []):
            self._walkable.add(Tile(coord[0], coord[1]))

    def description(self): return f"file map ({self.path})"
