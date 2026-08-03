#!/usr/bin/env python3
"""Extract map data from Godot FirstScene.tscn and tiles.tres files.

Parses the PackedByteArray tile map data and tile set custom data
to generate a map_data.json file that the Python engine can load.

Usage: python extract_map.py [--scene PATH] [--tileset PATH] [--output PATH]
"""

import argparse
import base64
import json
import os
import struct
import sys


def parse_packed_bytearray(b64_str: str) -> list[tuple[int, int, int]]:
    """Parse Godot 4 TileMapLayer PackedByteArray (base64-encoded).

    Godot 4.3+ format for TileMapLayer: each cell is 12 bytes:
      int32 x, int32 y, uint32 (source_id | (atlas_x << 16) | (atlas_y << 24) | (alt << 31))
      Actually: uint32 packed = source_id | (atlas_coords.x << 8) | (atlas_coords.y << 16) | (alternative_tile << 24)

    Returns list of (x, y, source_id).
    """
    raw = base64.b64decode(b64_str)
    cells = []
    # Each cell = 3 uint32 (12 bytes) — x, y, packed_tile
    fmt = "<3I"
    for i in range(0, len(raw), 12):
        chunk = raw[i:i+12]
        if len(chunk) < 12:
            break
        x, y, packed = struct.unpack(fmt, chunk)
        source_id = packed & 0xFF
        cells.append((x, y, source_id))
    return cells


def parse_tileset(tres_path: str) -> dict[tuple[int, int], bool]:
    """Parse tiles.tres to find which atlas tiles are walkable.

    Returns dict mapping (atlas_x, atlas_y) -> is_walkable.
    """
    walkable_map = {}
    try:
        with open(tres_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Warning: tileset file not found at {tres_path}")
        return walkable_map

    import re
    # Match: "X:Y/source_id/custom_data_0 = true"
    # Pattern: optional whitespace, digits:digits/source_id/custom_data_0 = VALUE
    pattern = r'(\d+):(\d+)/(\d+)/custom_data_0\s*=\s*(\w+)'
    for match in re.finditer(pattern, content):
        atlas_x = int(match.group(1))
        atlas_y = int(match.group(2))
        value = match.group(4).lower()
        walkable_map[(atlas_x, atlas_y)] = (value == "true")

    return walkable_map


def generate_map(scene_path: str, tileset_path: str) -> dict:
    """Generate map_data dict from scene and tileset files."""
    # Parse tileset for walkable info
    walkable_tiles = parse_tileset(tileset_path)
    print(f"Found {len(walkable_tiles)} tile definitions in tileset "
          f"({sum(1 for v in walkable_tiles.values() if v)} walkable)")

    # Parse scene for tile placements
    with open(scene_path, 'r') as f:
        scene_content = f.read()

    # Extract the PackedByteArray from tile_map_data
    import re
    match = re.search(r'tile_map_data\s*=\s*PackedByteArray\("([^"]+)"\)', scene_content)
    if not match:
        print("Warning: Could not find tile_map_data in scene file")
        # Try to find tile references another way
        return _fallback_map()

    b64_data = match.group(1)
    cells = parse_packed_bytearray(b64_data)
    print(f"Parsed {len(cells)} cells from scene tile_map_data")

    if not cells:
        return _fallback_map()

    # Determine map bounds
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x + 1
    height = max_y - min_y + 1

    # Convert cells to (atlas_x, atlas_y) from source_id
    # In Godot 4 tile map format, the packed field contains atlas coords
    # Actually, looking at the raw bytes more carefully:
    # The packing is: lower byte = source_id, next byte = atlas_x, next byte = atlas_y
    # Let's reprocess the cells

    # Re-parse with proper atlas coordinate extraction
    raw = base64.b64decode(b64_data)
    cell_atlas = {}  # (x, y) -> (atlas_x, atlas_y)
    fmt = "<3I"
    for i in range(0, len(raw), 12):
        chunk = raw[i:i+12]
        if len(chunk) < 12:
            break
        x, y, packed = struct.unpack(fmt, chunk)
        atlas_x = (packed >> 8) & 0xFF
        atlas_y = (packed >> 16) & 0xFF
        source_id = packed & 0xFF
        cell_atlas[(x, y)] = (atlas_x, atlas_y)

    # Build walkable set and ASCII grid
    walkable_coords = []
    ascii_grid = []
    for y in range(min_y, max_y + 1):
        line = ""
        for x in range(min_x, max_x + 1):
            atlas = cell_atlas.get((x, y))
            if atlas and walkable_tiles.get(atlas, False):
                line += "."
                walkable_coords.append([x, y])
            else:
                line += "#"
        ascii_grid.append(line)

    walkable_count = len(walkable_coords)
    print(f"Grid: {width}x{height}, {walkable_count} walkable tiles")

    if walkable_count == 0:
        print("Warning: No walkable tiles found. All tiles might be non-walkable or parsing failed.")
        print(f"Tileset walkable keys: {[(k, v) for k, v in walkable_tiles.items() if v]}")
        print(f"Sample cell atlas mappings: {dict(list(cell_atlas.items())[:5])}")

    return {
        "min_x": min_x, "max_x": max_x,
        "min_y": min_y, "max_y": max_y,
        "width": width, "height": height,
        "walkable": walkable_coords,
        "ascii_grid": ascii_grid,
        "walkable_count": walkable_count,
    }


def _fallback_map() -> dict:
    """Return a minimal open arena map for testing."""
    width, height = 10, 10
    ascii_grid = []
    walkable = []
    for y in range(height):
        line = ""
        for x in range(width):
            # Border walls, open inside
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                line += "#"
            else:
                line += "."
                walkable.append([x, y])
        ascii_grid.append(line)
    print(f"Using fallback map: {width}x{height}, {len(walkable)} walkable tiles")
    return {
        "min_x": 0, "max_x": width - 1,
        "min_y": 0, "max_y": height - 1,
        "width": width, "height": height,
        "walkable": walkable,
        "ascii_grid": ascii_grid,
        "walkable_count": len(walkable),
    }


def main():
    parser = argparse.ArgumentParser(description="Extract Among-I map data from Godot files")
    parser.add_argument("--scene", default="among-i/FirstScene.tscn",
                        help="Path to FirstScene.tscn")
    parser.add_argument("--tileset", default="among-i/tiles.tres",
                        help="Path to tiles.tres")
    parser.add_argument("--output", default="AgentControllers/map_data.json",
                        help="Output JSON path")
    args = parser.parse_args()

    # Resolve paths relative to project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    scene_path = os.path.join(project_root, "..", args.scene)
    tileset_path = os.path.join(project_root, "..", args.tileset)
    output_path = os.path.join(project_root, args.output)
    # Clean output path
    output_path = os.path.normpath(os.path.join(project_root, "..", args.output))

    scene_path = os.path.normpath(scene_path)
    tileset_path = os.path.normpath(tileset_path)

    if not os.path.exists(scene_path):
        print(f"Error: Scene file not found: {scene_path}")
        print(f"  Run from project root: python AgentControllers/extract_map.py")
        sys.exit(1)

    map_data = generate_map(scene_path, tileset_path)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(map_data, f, indent=2)

    print(f"Map data written to {output_path}")
    print(f"  Grid: {map_data['width']}x{map_data['height']}")
    print(f"  Walkable: {map_data['walkable_count']}")
    for row in map_data["ascii_grid"]:
        print(f"  {row}")


if __name__ == "__main__":
    main()
