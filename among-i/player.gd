# Player.gd
extends CharacterBody2D

var speed = 200

@onready var speech_bubble = get_node("SpeechBubble")

@export var tile_map: TileMapLayer  # Drag your TileMapLayer here in the Inspector
@export var move_speed: float = 0.2 # Time in seconds to move one tile

var is_moving: bool = false

var tile: Vector2i

## Call this function to move the player to a specific tile coordinate (e.g., Vector2i(5, 3))
func move_to_tile(target_tile_coords: Vector2i):
	if is_moving:
		return # Prevent starting a new move while already in motion
		
	var cords: Vector2i = target_tile_coords
	
	# 1. Check if the tile is actually walkable (optional but recommended)
	if not _is_tile_walkable(cords):
		print("Target tile is blocked!")
		#return
		
	tile = cords
	
	#cords = Vector2i(0,0)

	# 2. Convert the Tile Coordinates (1, 1) to World Position (16, 16)
	# map_to_local returns the center of the tile
	var target_world_position = tile_map.map_to_local(cords) + Vector2(100,-80)
	
	print(target_world_position)
	
	# 3. Use a Tween to animate the movement
	is_moving = true
	var tween = create_tween()
	
	# Set transition to SINE and ease to IN_OUT for a polished "slide" feel
	tween.set_trans(Tween.TRANS_SINE)
	tween.set_ease(Tween.EASE_IN_OUT)
	
	tween.tween_property(self, "global_position", target_world_position, move_speed)
	
	# 4. Reset the moving flag when finished
	tween.finished.connect(func(): is_moving = false)

## Helper to check custom data or if the tile exists
func _is_tile_walkable(coords: Vector2i) -> bool:
	var data = tile_map.get_cell_tile_data(coords)
	if data == null: 
		return false # No tile there
	
	# Assumes you have a Custom Data Layer named "walkable" in your TileSet
	return data.get_custom_data("walkable")
	
func _ready():
	# Snap to the nearest tile center immediately
	var current_tile = tile_map.local_to_map(global_position)
	global_position = tile_map.map_to_local(current_tile)

func _process(_delta):
	if speech_bubble != null and speech_bubble.visible:
		# Center the bubble horizontally and keep it above the sprite
		speech_bubble.position.x = -speech_bubble.size.x / 2.0
		speech_bubble.position.y = -(speech_bubble.size.y + 45.0)
