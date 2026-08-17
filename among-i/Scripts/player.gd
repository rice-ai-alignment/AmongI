# Player.gd
extends CharacterBody2D

var speed = 200

@onready var speech_bubble = get_node("SpeechBubble")

var action_label: Label  # recent-actions list above the head

@export var tile_map: TileMapLayer  # Drag your TileMapLayer here in the Inspector
@export var move_speed: float = .8 # Time in seconds to move one tile

var is_moving: bool = false
var is_dead: bool = false
var walk_tween: Tween = null
var frame_tween: Tween = null

const NO_PENDING := Vector2i(-99999, -99999)
var pending_tile: Vector2i = NO_PENDING  # queued move target while mid-tween

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
	pending_tile = NO_PENDING
	tile = target_tile_coords
	self.global_position = get_tile_position(target_tile_coords)

func set_dead():
	"""Turn this player into a visible corpse (dead sprite row, no movement)."""
	is_dead = true
	pending_tile = NO_PENDING
	# Stop any in-flight walk animation so the corpse pose sticks
	if frame_tween != null and frame_tween.is_valid():
		frame_tween.kill()
	if walk_tween != null and walk_tween.is_valid():
		walk_tween.kill()
	is_moving = false
	var sprite = get_node("Sprite2D")
	sprite.modulate = Color(0.22, 0.22, 0.28)
	sprite.frame_coords.y = 5   # dead body row in the spritesheet
	sprite.frame_coords.x = 0

func set_alive():
	"""Restore a corpse to a living player."""
	is_dead = false
	var sprite = get_node("Sprite2D")
	sprite.modulate = Color(1, 1, 1)
	sprite.frame_coords.y = idle_row
	sprite.frame_coords.x = 0

func move_to_tile(target_tile_coords: Vector2i):
	if is_dead:
		return false
	if is_moving:
		# Don't drop the move — queue it and apply when the tween finishes
		if target_tile_coords != tile:
			pending_tile = target_tile_coords
		return false

	tile = target_tile_coords
	var sprite = get_node("Sprite2D")

	var target_world_position = get_tile_position(target_tile_coords)

	is_moving = true
	walk_tween = create_tween()

	# 1. Flip Sprite based on direction
	#if target_world_position.x != global_position.x:
		#sprite.flip_h = target_world_position.x < global_position.x

	# 2. Parallel Tween: Move Body + Animate Frames
	walk_tween.set_parallel(true)

	# A. The actual movement
	walk_tween.tween_property(self, "global_position", target_world_position, move_speed)\
		.set_trans(Tween.TRANS_LINEAR)\
		.set_ease(Tween.EASE_IN_OUT)

	# B. The Frame Animation
	# We animate the 'x' of frame_coords from 0 to the last frame
	sprite.frame_coords.y = walk_row # Switch to the walking row
	frame_tween = create_tween()
	frame_tween.set_loops(2) # Repeat the walk cycle twice during the slow move
	frame_tween.set_trans(Tween.TRANS_LINEAR)
	frame_tween.tween_property(sprite, "frame_coords:y", frame_count - 1, move_speed / 2.0)\
		.from(0) # Start at frame 0

	# 3. Reset to Idle when done
	frame_tween.finished.connect(func():
		is_moving = false
		sprite.frame_coords.y = idle_row
		#sprite.frame_coords.x = 0
		# Apply any move that was queued while the tween ran
		if pending_tile != NO_PENDING:
			var next_tile = pending_tile
			pending_tile = NO_PENDING
			move_to_tile(next_tile)
	)

	return true

func show_message(text: String):
	"""Show a speech bubble. Empty messages are ignored — the bubble only
	appears when the agent actually says something, and the next message
	replaces it in place (it never auto-hides)."""
	if speech_bubble == null:
		return
	if text.strip_edges() == "":
		return
	var label = speech_bubble.get_child(0)
	if label:
		label.text = text
	speech_bubble.visible = true

func _ready():
	# Snap to the nearest tile center immediately
	var current_tile = tile_map.local_to_map(global_position)
	global_position = tile_map.map_to_local(current_tile)

	# Start on the idle frame explicitly (row 0, frame 0)
	var sprite = get_node("Sprite2D")
	sprite.frame_coords.y = idle_row
	sprite.frame_coords.x = 0

	# Recent-actions label above the head (created in code — no scene edits)
	action_label = Label.new()
	action_label.name = "ActionLabel"
	action_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	action_label.add_theme_font_size_override("font_size", 22)
	action_label.add_theme_color_override("font_color", Color(0.92, 0.95, 0.92))
	action_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	action_label.add_theme_constant_override("outline_size", 6)
	action_label.size = Vector2(380, 0)
	action_label.position = Vector2(-190, -360)
	add_child(action_label)

func set_recent_actions(lines: Array) -> void:
	"""Show the agent's most recent actions above their head."""
	if action_label == null:
		return
	action_label.text = "\n".join(lines)

func _process(_delta):
	if speech_bubble != null and speech_bubble.visible:
		# Center the bubble horizontally and keep it above the sprite
		speech_bubble.position.x = -speech_bubble.size.x / 2.0
		speech_bubble.position.y = -(speech_bubble.size.y + 45.0)
