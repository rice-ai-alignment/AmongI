"""map_visualizer.py — Renders an ASCII world view around a tile position."""

from __future__ import annotations

from position import Tile


class MapVisualizer:
    """Provides ASCII world-view strings for an agent at a given position."""

    def __init__(self, map_data):
        self._map = map_data

    def render(self, center: Tile, radius: int = 5) -> str:
        """Return a (radius*2+1) × (radius*2+1) ASCII grid centered on `center`.
        '@' marks the agent, '.' is walkable, '#' is a wall/obstacle."""
        lines = []
        for dy in range(-radius, radius + 1):
            row = ""
            for dx in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    row += "@"
                else:
                    row += "." if self._map.is_walkable(center.x + dx, center.y + dy) else "#"
            lines.append(row)
        return "\n".join(lines)
