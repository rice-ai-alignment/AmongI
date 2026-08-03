# export_map.gd — One-shot tool to export the walkable tile grid as JSON
# Usage:
#   1. Attach this script to a Node in the scene (or run from Script Editor)
#   2. Make sure tile_map references the TileMapLayer
#   3. Run the scene — map_data.json will be written to the AgentControllers/ directory
extends Node

@export var tile_map: TileMapLayer

func _ready():
	if tile_map == null:
		print("ERROR: tile_map not assigned. Drag the TileMapLayer node here.")
		return

	var min_x = 9999; var max_x = -9999
	var min_y = 9999; var max_y = -9999
	var walkable_coords = []

	# Scan all used cells in the tile map
	var used_cells = tile_map.get_used_cells()
	print("Scanning %d used cells..." % used_cells.size())

	for cell in used_cells:
		var x = cell.x; var y = cell.y
		min_x = min(min_x, x); max_x = max(max_x, x)
		min_y = min(min_y, y); max_y = max(max_y, y)

		var data = tile_map.get_cell_tile_data(cell)
		if data and data.get_custom_data("walkable"):
			walkable_coords.append([x, y])

	var width = max_x - min_x + 1
	var height = max_y - min_y + 1

	# Build ASCII grid (y increases downward in Godot)
	var ascii_grid = []
	for y in range(min_y, max_y + 1):
		var line = ""
		for x in range(min_x, max_x + 1):
			var cell = Vector2i(x, y)
			var data = tile_map.get_cell_tile_data(cell)
			if data and data.get_custom_data("walkable"):
				line += "."
			else:
				line += "#"
		ascii_grid.append(line)

	var output = {
		"min_x": min_x, "max_x": max_x,
		"min_y": min_y, "max_y": max_y,
		"width": width, "height": height,
		"walkable": walkable_coords,
		"ascii_grid": ascii_grid,
		"tile_count": used_cells.size(),
		"walkable_count": walkable_coords.size(),
	}

	var json_str = JSON.stringify(output, "\t")
	var path = "res://../AgentControllers/map_data.json"
	var file = FileAccess.open(path, FileAccess.WRITE)
	if file:
		file.store_string(json_str)
		file.close()
		print("Exported %d walkable tiles (out of %d total) to %s" % [walkable_coords.size(), used_cells.size(), path])
		print("Grid size: %dx%d (x: %d-%d, y: %d-%d)" % [width, height, min_x, max_x, min_y, max_y])
	else:
		print("ERROR: Could not write to %s" % path)

	# get_tree().quit()
