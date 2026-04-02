# Player.gd
extends CharacterBody2D

var speed = 200

@onready var speech_bubble = get_node("SpeechBubble")

@export var tile_map: TileMapLayer  # Drag your TileMapLayer here in the Inspector
@export var move_speed: float = .8 # Time in seconds to move one tile

var is_moving: bool = false

@export var tile: Vector2i
## Call this function to move the player to a specific tile coordinate (e.g., Vector2i(5, 3))
# Assumes you have an AnimationPlayer node as a child of the Player

# Increase this number to move slower (e.g., 0.8 seconds per tile instead of 0.2)

@export var walk_row: int = 1        # The Y-coordinate in your SpriteSheet for walking
@export var idle_row: int = 0        # The Y-coordinate in your SpriteSheet for idle
@export var frame_count: int = 4     # How many frames are in your walking animation loop

func get_tile_position(target_tile_coords: Vector2i):
	return tile_map.map_to_local(target_tile_coords) + Vector2(100, -80)

func set_tile_position(target_tile_coords: Vector2i):
	tile = target_tile_coords
	self.global_position = get_tile_position(target_tile_coords)

func move_to_tile(target_tile_coords: Vector2i):
	if is_moving:
		return false
		
	tile = target_tile_coords
		
	var sprite = get_node("Sprite2D")
		
	if not _is_tile_walkable(target_tile_coords):
		return false

	var target_world_position = get_tile_position(target_tile_coords)
	
	is_moving = true
	var tween = create_tween()
	
	# 1. Flip Sprite based on direction
	#if target_world_position.x != global_position.x:
		#sprite.flip_h = target_world_position.x < global_position.x

	# 2. Parallel Tween: Move Body + Animate Frames
	tween.set_parallel(true)
	
	# A. The actual movement
	tween.tween_property(self, "global_position", target_world_position, move_speed)\
		.set_trans(Tween.TRANS_LINEAR)\
		.set_ease(Tween.EASE_IN_OUT)
	
	# B. The Frame Animation
	# We animate the 'x' of frame_coords from 0 to the last frame
	sprite.frame_coords.y = walk_row # Switch to the walking row
	var frame_tween = create_tween()
	frame_tween.set_loops(2) # Repeat the walk cycle twice during the slow move
	frame_tween.set_trans(Tween.TRANS_LINEAR)
	frame_tween.tween_property(sprite, "frame_coords:y", frame_count - 1, move_speed / 2.0)\
		.from(0) # Start at frame 0
	
	# 3. Reset to Idle when done
	frame_tween.finished.connect(func():
		is_moving = false
		sprite.frame_coords.y = idle_row
		#sprite.frame_coords.x = 0
	)
	
	return true

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
