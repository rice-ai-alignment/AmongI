# Player.gd
extends CharacterBody2D

var speed = 200

@onready var speech_bubble = get_node("SpeechBubble")
@onready var name_label = get_node("NameLabel")

var action_label: Label  # recent-actions list above the head

@export var tile_map: TileMapLayer  # Drag your TileMapLayer here in the Inspector
@export var move_speed: float = 1.5 # Time in seconds to move one tile

var is_moving: bool = false
var is_dead: bool = false
var walk_tween: Tween = null
var frame_tween: Tween = null
var idle_tween: Tween = null

# Server sets these at spawn:
var spread_index: int = 0     # per-agent visual offset so they never overlap
var is_imposter: bool = false # imposter chats render red

const NO_PENDING := Vector2i(-99999, -99999)
var pending_tile: Vector2i = NO_PENDING  # queued move target while mid-tween

@export var tile: Vector2i
## Call this function to move the player to a specific tile coordinate (e.g., Vector2i(5, 3))
# Assumes you have an AnimationPlayer node as a child of the Player

# Increase this number to move slower (e.g., 0.8 seconds per tile instead of 0.2)

@export var walk_row: int = 1        # The Y-coordinate in your SpriteSheet for walking
@export var idle_row: int = 0        # The Y-coordinate in your SpriteSheet for idle
@export var frame_count: int = 4     # How many frames are in your walking animation loop

# The generated sheet (make_sprites.py) stacks one 3-row band per color,
# in AGENT_COLORS order (0 idle · 1 walk · 2 dead). Server.gd sets
# color_band at spawn.
const ROWS_PER_COLOR := 3
var color_band: int = 0

func _row(base: int) -> int:
	return color_band * ROWS_PER_COLOR + base

func _start_idle_anim() -> void:
	"""Cycle the 4 idle columns slowly (breathing) while standing still."""
	if is_dead or is_moving:
		return
	if idle_tween != null and idle_tween.is_valid():
		idle_tween.kill()
	var sprite = get_node("Sprite2D")
	idle_tween = create_tween()
	idle_tween.set_loops()  # infinite
	idle_tween.tween_property(sprite, "frame_coords:x", frame_count - 1, 1.2)\
		.from(0)

# Per-agent spread: agents on the same tile nudge apart by their index
# so sprites never perfectly overlap.
const SPREAD_OFFSETS: Array[Vector2] = [
	Vector2(0, 0), Vector2(26, 22), Vector2(-26, 22), Vector2(26, -22), Vector2(-26, -22),
	Vector2(0, 34), Vector2(0, -34), Vector2(38, 0), Vector2(-38, 0), Vector2(18, 18),
]

func get_tile_position(target_tile_coords: Vector2i):
	return tile_map.map_to_local(target_tile_coords) \
		+ Vector2(0, -80) \
		+ SPREAD_OFFSETS[spread_index % SPREAD_OFFSETS.size()]

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
	if idle_tween != null and idle_tween.is_valid():
		idle_tween.kill()
	is_moving = false
	var sprite = get_node("Sprite2D")
	sprite.modulate = Color(0.22, 0.22, 0.28)
	sprite.frame_coords.y = _row(2)   # dead body row in the spritesheet
	sprite.frame_coords.x = 0

func set_alive():
	"""Restore a corpse to a living player."""
	is_dead = false
	var sprite = get_node("Sprite2D")
	sprite.modulate = Color(1, 1, 1)
	sprite.frame_coords.y = _row(idle_row)
	sprite.frame_coords.x = 0
	_start_idle_anim()

func move_to_tile(target_tile_coords: Vector2i):
	if is_dead:
		return false
	if is_moving:
		# Don't drop the move — queue it and apply when the tween finishes
		if target_tile_coords != tile:
			pending_tile = target_tile_coords
		return false

	# Walking replaces the idle animation
	if idle_tween != null and idle_tween.is_valid():
		idle_tween.kill()

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
	sprite.frame_coords.y = _row(walk_row) # Switch to the walking row
	frame_tween = create_tween()
	frame_tween.set_loops() # loop the walk cycle until the move finishes
	frame_tween.set_trans(Tween.TRANS_LINEAR)
	frame_tween.tween_property(sprite, "frame_coords:x", frame_count - 1, move_speed / 4.0)\
		.from(0) # Start at frame 0

	# 3. Reset to Idle when the MOVE finishes (the frame tween loops on)
	walk_tween.finished.connect(func():
		if frame_tween != null and frame_tween.is_valid():
			frame_tween.kill()
		is_moving = false
		sprite.frame_coords.y = _row(idle_row)
		sprite.frame_coords.x = 0
		# Apply any move that was queued while the tween ran
		if pending_tile != NO_PENDING:
			var next_tile = pending_tile
			pending_tile = NO_PENDING
			move_to_tile(next_tile)
		else:
			_start_idle_anim()
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
	# Snap to the nearest tile center immediately (with the per-agent
	# spread offset so overlapping agents separate right away)
	var current_tile = tile_map.local_to_map(global_position)
	global_position = get_tile_position(current_tile)

	# Start on the idle frame explicitly (row 0, frame 0) and begin the
	# breathing animation
	var sprite = get_node("Sprite2D")
	sprite.frame_coords.y = _row(idle_row)
	sprite.frame_coords.x = 0
	_start_idle_anim()

	# Imposters get red chat bubbles so their messages stand out
	if is_imposter and speech_bubble != null:
		var style := StyleBoxFlat.new()
		style.bg_color = Color(0.45, 0.10, 0.10, 0.96)
		style.border_color = Color(0.75, 0.15, 0.15, 1)
		style.set_border_width_all(1)
		style.set_corner_radius_all(6)
		style.content_margin_left = 8.0
		style.content_margin_top = 5.0
		style.content_margin_right = 8.0
		style.content_margin_bottom = 5.0
		speech_bubble.add_theme_stylebox_override("panel", style)
		var lbl = speech_bubble.get_child(0)
		if lbl is Label:
			lbl.add_theme_color_override("font_color", Color(1, 0.85, 0.85))

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

func set_actions_visible(v: bool) -> void:
	"""Show/hide the recent-actions debug text ([H] in the renderer)."""
	if action_label != null:
		action_label.visible = v

func _process(_delta):
	# Keep text UI at constant screen size regardless of camera zoom:
	# counter-scale the bubble, name, and action labels by 1/zoom.
	var cam := get_viewport().get_camera_2d()
	var s := 1.0
	if cam != null:
		s = 1.0 / maxf(cam.zoom.x, 0.05)
	if speech_bubble != null:
		speech_bubble.scale = Vector2(s, s)
	if name_label != null:
		name_label.scale = Vector2(s, s)
	if action_label != null:
		action_label.scale = Vector2(s, s)

	if speech_bubble != null and speech_bubble.visible:
		# Center the bubble horizontally and keep it above the sprite
		speech_bubble.position.x = -speech_bubble.size.x / 2.0
		speech_bubble.position.y = -(speech_bubble.size.y + 45.0)
