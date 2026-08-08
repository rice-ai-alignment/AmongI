"""position.py — Simple 2D tile coordinate."""

from __future__ import annotations

import math


class Tile:
    """A 2D integer coordinate on the map grid."""

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    def __eq__(self, other):
        return isinstance(other, Tile) and self.x == other.x and self.y == other.y

    def __hash__(self):
        return hash((self.x, self.y))

    def __repr__(self):
        return f"Tile({self.x}, {self.y})"

    def __iter__(self):
        return iter((self.x, self.y))

    def distance_to(self, other: Tile) -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def delta(self, other: Tile) -> tuple[int, int]:
        """Return (dx, dy) from self to other, with dy flipped for Y-up display."""
        return (other.x - self.x, self.y - other.y)

    def copy(self) -> Tile:
        return Tile(self.x, self.y)
