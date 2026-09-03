# Server.gd — Pure renderer for the Among-I simulation.
# Receives render events from the Python game engine via WebSocket (port 8081)
# and drives the visual presentation: player sprites, movement animation,
# chat HUD, camera auto-framing.
#
# All game logic lives in engine.py. Godot only renders.

extends Node

signal event_received(ev: Dictionary)

@export var player_scene: PackedScene = preload("res://Player.tscn")
@export var tile_map: TileMapLayer
@onready var chat_box = $ChatBox
@onready var camera: Camera2D = $Camera2D

# ── Render WebSocket ─────────────────────────────────────────────────────

var _server := TCPServer.new()
var _render_port := 8081
var _render_peer: WebSocketPeer = null
var _peer_id: int = -1
var _remote_mode: bool = false
var _remote_url: String = ""
var _remote_retry_at: float = 0.0

# ── Player tracking (agent_id -> Player node) ────────────────────────────

var _players: Dictionary = {}       # agent_id -> Player node
var _player_names: Dictionary = {}  # agent_id -> display name
var _player_colors: Dictionary = {} # agent_id -> color_index
var _game_active: bool = false

# ── Colors (must match engine.py's AGENT_COLORS) ─────────────────────────

const AGENT_COLORS = [
	"#C51111", "#132ED2", "#117F2D", "#ED54BB", "#EF7D0E",
	"#C8CD00", "#3F474E", "#D85A30", "#378ADD", "#1D9E75"
]

# ── Camera (auto-framing + freecam) ─────────────────────────────────────

var camera_mode: String = "auto"   # "auto" | "free"
var _cam_label: Label
var _state_label: Label = null      # top-center game state (STARTING/PLAYING/VOTING/ENDED)
var _show_actions: bool = true      # [H] toggles per-agent recent-actions text

var _camera_padding: float = 500.0
var _camera_min_zoom: float = 0.05
var _camera_max_zoom: float = 8.0
var _camera_smooth_speed: float = 4.0
var _camera_min_world_size: float = 400.0

var _freecam_speed: float = 900.0   # px/sec at zoom 1

# ── Chat ─────────────────────────────────────────────────────────────────

const MAX_CHAT_MESSAGES = 50

# ── Playback mode flags ────────────────────────────────────────────────────

var instant_mode: bool = false   # skip tweens, snap positions
var silent: bool = false         # suppress debug prints during fast-forward

# ── Per-agent recent actions (shown above their heads) ────────────────────

const MAX_RECENT_ACTIONS := 3
var _recent_actions: Dictionary = {}   # agent_id -> Array[String]

# ── Voting screen (live board: who voted for what) ────────────────────────

var _voting_layer: CanvasLayer = null
var _voting_panel: PanelContainer = null
var _voting_rows_vbox: VBoxContainer = null
var _voting_countdown: Label = null
var _voting_result_lbl: Label = null
var _voting_rows: Dictionary = {}      # agent_id -> {"vote": Label}
var _voting_deadline_ms: int = 0       # Time.get_ticks_msec() deadline

# ── Initialization ───────────────────────────────────────────────────────

func _ready():
	# Camera mode HUD label
	var cam_layer := CanvasLayer.new()
	cam_layer.name = "CamHudLayer"
	add_child(cam_layer)
	_cam_label = Label.new()
	_cam_label.position = Vector2(16, 16)
	_cam_label.add_theme_font_size_override("font_size", 18)
	_cam_label.add_theme_color_override("font_color", Color(0.9, 0.95, 0.9))
	_cam_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	_cam_label.add_theme_constant_override("outline_size", 5)
	cam_layer.add_child(_cam_label)
	_update_camera_label()

	# Voting board HUD
	_build_voting_screen()

	# Top-center game state label
	_state_label = Label.new()
	_state_label.name = "GameStateLabel"
	_state_label.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_state_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_state_label.position = Vector2(0, 12)
	_state_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_state_label.add_theme_font_size_override("font_size", 22)
	_state_label.add_theme_color_override("font_color", Color(0.31, 0.91, 0.49))
	_state_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
	_state_label.add_theme_constant_override("outline_size", 6)
	cam_layer.add_child(_state_label)
	_set_game_state("WAITING FOR GAME…", Color(0.62, 0.72, 0.62))

	# If PlaybackController loaded a file (child _ready runs first), skip listening
	if has_node("PlaybackController") and $PlaybackController.is_file_mode():
		print("[Renderer] File replay mode — skipping WebSocket listen")
		return
	start_listening()


# ── Voting screen ─────────────────────────────────────────────────────────

func _build_voting_screen():
	_voting_layer = CanvasLayer.new()
	_voting_layer.name = "VotingScreenLayer"
	_voting_layer.layer = 5
	_voting_layer.visible = false
	add_child(_voting_layer)

	_voting_panel = PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.05, 0.08, 0.05, 0.94)
	style.border_color = Color(0.31, 0.91, 0.49, 0.55)
	style.set_border_width_all(1)
	style.set_corner_radius_all(6)
	style.content_margin_left = 22.0
	style.content_margin_right = 22.0
	style.content_margin_top = 14.0
	style.content_margin_bottom = 14.0
	_voting_panel.add_theme_stylebox_override("panel", style)
	_voting_panel.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_voting_panel.position = Vector2(0, 110)
	_voting_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_voting_layer.add_child(_voting_panel)

	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	_voting_panel.add_child(vb)

	var title := Label.new()
	title.text = "══ EMERGENCY MEETING — VOTING ══"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 24)
	title.add_theme_color_override("font_color", Color(0.31, 0.91, 0.49))
	title.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
	title.add_theme_constant_override("outline_size", 6)
	vb.add_child(title)

	_voting_countdown = Label.new()
	_voting_countdown.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_voting_countdown.add_theme_font_size_override("font_size", 16)
	_voting_countdown.add_theme_color_override("font_color", Color(0.62, 0.72, 0.62))
	vb.add_child(_voting_countdown)

	_voting_rows_vbox = VBoxContainer.new()
	_voting_rows_vbox.add_theme_constant_override("separation", 4)
	vb.add_child(_voting_rows_vbox)

	_voting_result_lbl = Label.new()
	_voting_result_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_voting_result_lbl.add_theme_font_size_override("font_size", 18)
	_voting_result_lbl.add_theme_color_override("font_color", Color(0.9, 0.62, 0.33))
	_voting_result_lbl.visible = false
	vb.add_child(_voting_result_lbl)


func _voting_show(ids: Array, timeout: float):
	for row in _voting_rows.values():
		row["row"].queue_free()
	_voting_rows.clear()
	for aid_v in ids:
		var aid := int(aid_v)
		var hb := HBoxContainer.new()
		hb.add_theme_constant_override("separation", 8)
		var dot := Label.new()
		dot.text = "●"
		var color_idx: int = _player_colors.get(aid, 0)
		dot.add_theme_color_override("font_color",
			Color(AGENT_COLORS[color_idx % AGENT_COLORS.size()]))
		dot.add_theme_font_size_override("font_size", 14)
		var name_lbl := Label.new()
		name_lbl.text = str(_player_names.get(aid, "?"))
		name_lbl.custom_minimum_size.x = 150
		name_lbl.add_theme_font_size_override("font_size", 16)
		name_lbl.add_theme_color_override("font_color", Color(0.93, 0.96, 0.93))
		var arrow := Label.new()
		arrow.text = "→"
		arrow.add_theme_color_override("font_color", Color(0.62, 0.72, 0.62))
		var vote_lbl := Label.new()
		vote_lbl.text = "…"
		vote_lbl.add_theme_font_size_override("font_size", 16)
		vote_lbl.add_theme_color_override("font_color", Color(0.31, 0.91, 0.49))
		hb.add_child(dot)
		hb.add_child(name_lbl)
		hb.add_child(arrow)
		hb.add_child(vote_lbl)
		_voting_rows_vbox.add_child(hb)
		_voting_rows[aid] = {"vote": vote_lbl, "row": hb}
	_voting_deadline_ms = Time.get_ticks_msec() + int(timeout * 1000.0)
	_voting_result_lbl.visible = false
	_voting_layer.visible = true


func _voting_set_vote(voter: String, choice: String):
	for aid in _voting_rows:
		if str(_player_names.get(aid, "")) == voter:
			_voting_rows[aid]["vote"].text = choice
			return


func _voting_show_result(tally_str: String, ejected: String):
	if _voting_layer == null:
		return
	_voting_result_lbl.text = "result: " + tally_str \
		+ (" — ejected: " + ejected if ejected != "" else "")
	_voting_result_lbl.visible = true


func _voting_hide():
	if _voting_layer != null:
		_voting_layer.visible = false


func _set_game_state(text: String, color: Color):
	if _state_label == null:
		return
	_state_label.text = text
	_state_label.add_theme_color_override("font_color", color)


func start_listening():
	# Remote relay mode — connect OUT to a server's render relay instead of
	# listening locally. Web export: /index.html?connect=wss://host:8081
	# Desktop: godot --path . -- --connect=ws://host:8081
	var connect_url = _remote_connect_url()
	if connect_url != "":
		_remote_mode = true
		_remote_url = connect_url
		_remote_connect()
		return

	var err = _server.listen(_render_port)
	if err == OK:
		print("[Renderer] Listening for engine on port ", _render_port)
	else:
		print("[Renderer] FATAL: Cannot bind port ", _render_port, " (error ", err, ")")
		print("[Renderer] Is another Godot instance or process using this port?")
		get_tree().quit(1)


func _remote_connect_url() -> String:
	if OS.has_feature("web"):
		return JavaScriptBridge.eval("new URLSearchParams(window.location.search).get('connect') || ''")
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--connect="):
			return a.substr(10)
	return ""


func _remote_connect():
	if _render_peer != null and _render_peer.get_ready_state() == WebSocketPeer.STATE_CONNECTING:
		return
	_render_peer = WebSocketPeer.new()
	var e = _render_peer.connect_to_url(_remote_url)
	if e != OK:
		print("[Renderer] Cannot connect to render relay: ", _remote_url, " (error ", e, ")")
		_render_peer = null
		return
	print("[Renderer] Remote relay mode — connecting to ", _remote_url)


func stop_listening():
	_server.stop()
	_render_peer = null
	_peer_id = -1
	print("[Renderer] Stopped listening")


func clear_world():
	_clear_all_players()
	chat_box.clear()
	_game_active = false

# ── Main loop ────────────────────────────────────────────────────────────

func _process(delta):
	_accept_connection()
	_poll_render_peer()

	# Voting countdown tick
	if _voting_layer != null and _voting_layer.visible and _voting_countdown != null:
		var left := maxi(0, int(ceil((_voting_deadline_ms - Time.get_ticks_msec()) / 1000.0)))
		_voting_countdown.text = "votes in: " + str(left) + "s"

	if camera_mode == "free":
		_update_freecam(delta)
	else:
		_update_camera(delta)


# ── Camera input / freecam ──────────────────────────────────────────────

func _update_camera_label():
	var base: String = "CAM: free — WASD move · wheel zoom · [F] auto" if camera_mode == "free" \
		else "CAM: auto — [F] freecam"
	_cam_label.text = base + (" · [H] actions on" if _show_actions else " · [H] actions off")


func _unhandled_input(event: InputEvent):
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F:
			camera_mode = "free" if camera_mode == "auto" else "auto"
			print("[Renderer] Camera mode: ", camera_mode)
			_update_camera_label()
			return
		if event.keycode == KEY_H:
			# Toggle the per-agent recent-actions debug text
			_show_actions = not _show_actions
			for p in _players.values():
				if is_instance_valid(p):
					p.set_actions_visible(_show_actions)
			print("[Renderer] Recent-actions text: ", "on" if _show_actions else "off")
			_update_camera_label()
			return

	if camera_mode != "free":
		return

	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera.zoom = (camera.zoom * 1.1).clamp(Vector2(_camera_min_zoom, _camera_min_zoom),
													Vector2(_camera_max_zoom, _camera_max_zoom))
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera.zoom = (camera.zoom / 1.1).clamp(Vector2(_camera_min_zoom, _camera_min_zoom),
													Vector2(_camera_max_zoom, _camera_max_zoom))


func _update_freecam(delta: float):
	var dir := Vector2.ZERO
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		dir.y -= 1
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		dir.y += 1
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		dir.x -= 1
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		dir.x += 1
	if dir != Vector2.ZERO:
		# Scale pan speed by zoom so it feels constant on screen
		var speed: float = _freecam_speed / maxf(camera.zoom.x, 0.001)
		camera.global_position += dir.normalized() * speed * delta


# ── Recent-action tracking ──────────────────────────────────────────────

func _record_action(aid: int, text: String):
	if aid < 0:
		return
	if not _recent_actions.has(aid):
		_recent_actions[aid] = []
	var arr: Array = _recent_actions[aid]
	arr.push_front(text)
	while arr.size() > MAX_RECENT_ACTIONS:
		arr.pop_back()
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].set_recent_actions(arr)

# ── WebSocket handling ───────────────────────────────────────────────────

func _accept_connection():
	if not _server.is_connection_available():
		return

	# Only accept if we don't have an active peer
	if _render_peer != null:
		var state = _render_peer.get_ready_state()
		if state == WebSocketPeer.STATE_OPEN:
			# Already connected — drain and discard the extra connection
			var _c = _server.take_connection()
			return
		elif state == WebSocketPeer.STATE_CONNECTING:
			# Handshake in progress — don't interrupt it
			return

	# Accept the new connection
	var conn = _server.take_connection()
	_render_peer = WebSocketPeer.new()
	_render_peer.accept_stream(conn)
	_peer_id = _render_peer.get_instance_id()
	print("[Renderer] Python engine connected (peer ", _peer_id, ")")

func _poll_render_peer():
	# Remote mode auto-reconnect
	if _remote_mode and _render_peer == null \
			and Time.get_ticks_msec() / 1000.0 >= _remote_retry_at:
		_remote_connect()

	if _render_peer == null:
		return

	_render_peer.poll()
	var state = _render_peer.get_ready_state()

	if state == WebSocketPeer.STATE_OPEN:
		while _render_peer.get_available_packet_count() > 0:
			var packet = _render_peer.get_packet().get_string_from_utf8()
			var event = JSON.parse_string(packet)
			if event:
				_handle_event(event)

	elif state == WebSocketPeer.STATE_CLOSED or state == WebSocketPeer.STATE_CLOSING:
		if _remote_mode:
			_render_peer = null
			_remote_retry_at = Time.get_ticks_msec() / 1000.0 + 2.0
			print("[Renderer] Relay disconnected — reconnecting in 2s")
		else:
			print("[Renderer] Python engine disconnected")
			_render_peer = null
			_peer_id = -1

# ── Event dispatcher ─────────────────────────────────────────────────────

func handle_event(event: Dictionary):
	"""Public entry point for PlaybackController (file replay and live accumulation)."""
	_handle_event(event)


func _handle_event(event: Dictionary):
	event_received.emit(event)

	var etype: String = event.get("type", "")
	if etype not in ["", "heartbeat"] and not silent:
		print("[Renderer] Received event type: ", etype)

	match etype:
		"heartbeat":
			pass

		# ── Game lifecycle ──

		"game_start":
			_ev_game_start(event)

		"game_end":
			_ev_game_end(event)

		"phase_change":
			_ev_phase_change(event)

		# ── Player lifecycle ──
		# Supports both render-protocol names and log-format names.

		"spawn_player":
			_ev_spawn_player(event)

		"move_player", "move":
			_ev_move_player(event)

		"player_died", "kill":
			_ev_player_died(event)

		"player_ejected", "eject":
			_ev_player_ejected(event)

		"player_respawn":
			_ev_player_respawn(event)

		# ── Combined per-agent actions (log format) ──

		"actions":
			_ev_actions(event)

		# ── Chat ──

		"chat", "say":
			_ev_chat(event)

		"system_message":
			_ev_system_message(event)

		# ── Voting ──

		"voting_start", "start":
			_ev_voting_start(event)

		"vote_cast":
			_ev_vote_cast(event)

		"voting_result", "result":
			_ev_voting_result(event)

		"map_data":
			_ev_map_data(event)

		_:
			print("[Renderer] Unknown event type: ", etype)

# ── Event handlers ───────────────────────────────────────────────────────

func _ev_game_start(ev: Dictionary):
	_clear_all_players()
	_voting_hide()
	_game_active = true

	for pdata in ev.get("players", []):
		_spawn_player_node(
			pdata.get("agent_id", -1),
			pdata.get("name", "?"),
			Vector2i(pdata.get("tile", [0, 0])[0],
					 pdata.get("tile", [0, 0])[1]),
			pdata.get("color_index", 0),
			pdata.get("agent_type", "")
		)
	# Already done by the chage state thing
	var gid = ev.get("game_id", "?")
	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Game started! (" + str(gid) + ")", ev.get("elapsed_ms", -1.0))
	_set_game_state("PLAYING", Color(0.31, 0.91, 0.49))

func _ev_game_end(ev: Dictionary):
	_game_active = false
	var winner = ev.get("winner", "?")
	var recap = ev.get("recap", {})
	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Game Over! " + str(winner) + " win!", ev.get("elapsed_ms", -1.0))
	print("[Renderer] Game ended — winner: ", winner, " recap: ", recap)
	_set_game_state("ENDED — " + str(winner).to_upper() + " WIN!", Color(0.95, 0.55, 0.55))
	_voting_hide()

func _ev_phase_change(ev: Dictionary):
	var phase = ev.get("phase", "?")
	var countdown = ev.get("countdown_sec", 0)
	match phase:
		"starting":
			chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Game starting in " + str(int(countdown)) + "s...", ev.get("elapsed_ms", -1.0))
			_set_game_state("STARTING — " + str(int(countdown)) + "s", Color(0.9, 0.62, 0.33))
			_voting_hide()
		"voting":
			chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: ══════ VOTING PHASE (" + str(int(countdown)) + "s) ══════", ev.get("elapsed_ms", -1.0))
			_set_game_state("VOTING — " + str(int(countdown)) + "s", Color(0.9, 0.62, 0.33))
		"playing":
			chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Playing!", ev.get("elapsed_ms", -1.0))
			_set_game_state("PLAYING", Color(0.31, 0.91, 0.49))
			_voting_hide()

func _ev_map_data(ev: Dictionary):
	var w = ev.get("width", 0)
	var h = ev.get("height", 0)
	var walkable = ev.get("walkable", [])
	var min_x = ev.get("min_x", 0)
	var min_y = ev.get("min_y", 0)
	print("[Renderer] Map received: ", w, "x", h, " (", walkable.size(), " walkable tiles)")
	if w <= 0 or h <= 0 or tile_map == null:
		return

	# Pick floor/wall tiles from the tileset by their custom "walkable" data.
	# No manual scene placement needed — the map is painted at runtime so the
	# visual always matches the engine's map.
	var floor_atlas := Vector2i(-1, -1)
	var wall_atlas := Vector2i(-1, -1)
	var ts: TileSet = tile_map.tile_set
	if ts:
		var src = ts.get_source(0) as TileSetAtlasSource
		if src:
			for i in src.get_tiles_count():
				var coords: Vector2i = src.get_tile_id(i)
				var td: TileData = src.get_tile_data(coords, 0)
				var is_walkable: bool = td != null and td.get_custom_data("walkable")
				if is_walkable and floor_atlas.x < 0:
					floor_atlas = coords
				elif not is_walkable and wall_atlas.x < 0:
					wall_atlas = coords
				if floor_atlas.x >= 0 and wall_atlas.x >= 0:
					break
	if floor_atlas.x < 0:
		floor_atlas = Vector2i(0, 6)   # fallback if custom data is missing
	if wall_atlas.x < 0:
		wall_atlas = Vector2i(0, 0)
	print("[Renderer] Painting map with floor=", floor_atlas, " wall=", wall_atlas)

	# Build walkable set (handles [[x,y],...] pairs and {x,y} dicts)
	var walk_set := {}
	for c in walkable:
		if c is Array and c.size() >= 2:
			walk_set[Vector2i(int(c[0]), int(c[1]))] = true
		elif c is Dictionary:
			walk_set[Vector2i(int(c.get("x", 0)), int(c.get("y", 0)))] = true

	# Repaint the whole map from the engine's grid
	tile_map.clear()
	for y in range(h):
		for x in range(w):
			var cell := Vector2i(min_x + x, min_y + y)
			if walk_set.has(cell):
				tile_map.set_cell(cell, 0, floor_atlas)
			else:
				tile_map.set_cell(cell, 0, wall_atlas)

# ── Player spawn / despawn ──

func _ev_spawn_player(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	var name = ev.get("name", "?")
	var tile = Vector2i(ev.get("tile", [0, 0])[0], ev.get("tile", [0, 0])[1])
	var color_idx = ev.get("color_index", 0)
	_spawn_player_node(aid, name, tile, color_idx)

func _spawn_player_node(aid: int, pname: String, tile: Vector2i, color_idx: int,
						agent_type: String = ""):
	# Remove existing node if re-spawning
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].queue_free()

	var player = player_scene.instantiate()
	player.name = "Agent_%d" % aid
	player.tile_map = tile_map

	# Everything below must be set BEFORE the node enters the tree so
	# _ready() can use it (color band, spread offset, imposter styling).
	var band = color_idx % AGENT_COLORS.size()
	player.color_band = band
	player.spread_index = aid
	player.is_imposter = agent_type.to_lower() in ["imposter", "impostor"]
	player.get_node("Sprite2D").modulate = Color(1, 1, 1, 1)

	add_child(player)
	player.set_tile_position(tile)
	player.set_actions_visible(_show_actions)

	# Set name label
	var name_label = player.get_node("NameLabel")
	if name_label:
		name_label.text = pname

	_players[aid] = player
	_player_names[aid] = pname
	_player_colors[aid] = color_idx

	print("[Renderer] Spawned player: ", pname, " (agent ", aid, ") at ", tile)

func _clear_all_players():
	for aid in _players.keys():
		var node = _players[aid]
		if is_instance_valid(node):
			node.queue_free()
	_players.clear()
	_player_names.clear()
	_player_colors.clear()
	_recent_actions.clear()

# ── Player movement ──

func _ev_move_player(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	if aid in _players and is_instance_valid(_players[aid]):
		var to_data = ev.get("to", [0, 0])
		var to: Vector2i
		if to_data is Dictionary:
			to = Vector2i(to_data.get("x", 0), to_data.get("y", 0))
		else:
			to = Vector2i(to_data[0], to_data[1])
		if instant_mode:
			_players[aid].set_tile_position(to)
		else:
			_players[aid].move_to_tile(to)

# ── Player death / ejection / respawn ──

func _ev_player_died(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	var cause = ev.get("cause", "kill")
	if aid in _players and is_instance_valid(_players[aid]):
		# Leave a visible corpse (dark tint) instead of hiding the player
		_players[aid].set_dead()
		print("[Renderer] Player ", _player_names.get(aid, "?"), " died (", cause, ")")
	# Record the kill on the killer's action list
	var killed_by = ev.get("killed_by", null)
	if killed_by != null:
		var victim := str(_player_names.get(aid, "?"))
		if killed_by is int or (killed_by is String and killed_by.is_valid_int()):
			_record_action(int(killed_by), "killed " + victim)
		else:
			for other_id in _player_names.keys():
				if str(_player_names[other_id]) == str(killed_by):
					_record_action(int(other_id), "killed " + victim)
					break

func _ev_player_ejected(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].visible = false
		print("[Renderer] Player ", _player_names.get(aid, "?"), " ejected")

func _ev_player_respawn(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	var tile = Vector2i(ev.get("tile", [0, 0])[0], ev.get("tile", [0, 0])[1])
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].set_alive()
		_players[aid].set_tile_position(tile)
		print("[Renderer] Player ", _player_names.get(aid, "?"), " respawned at ", tile)

# ── Chat ──

func _ev_chat(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	var message: String = ev.get("message", "")
	if message == "":
		return
	var pname = ev.get("actor", ev.get("name", "?"))
	var color_idx = _player_colors.get(aid, 0)
	var color_str = AGENT_COLORS[color_idx % AGENT_COLORS.size()]

	# Show speech bubble on player node (auto-hides after a few seconds)
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].show_message(message)

	# Add to chat HUD
	var bbcode = "[b][color=%s]%s[/color][/b]: %s" % [color_str, pname, message]
	chat_box.add_message(bbcode, ev.get("elapsed_ms", -1.0))

	# Track in the recent-actions list above the head
	_record_action(aid, "say: " + message)

# ── Combined per-agent actions ────────────────────────────────────────

func _ev_actions(ev: Dictionary):
	"""Handle a combined actions event (log format: one event per agent per tick)."""
	var aid = int(ev.get("agent_id", -1))
	var pname = ev.get("actor", _player_names.get(aid, "?"))
	var actions: Array = ev.get("actions", [])
	if not silent:
		print("[Renderer] _ev_actions: agent=", aid, " pname=", pname, " actions=", actions.size())

	for act in actions:
		var atype: String = act.get("type", "")
		if not silent:
			print("[Renderer]   sub-action: ", atype, " act=", act)
		match atype:
			"move":
				var to_data = act.get("to", {})
				var to: Vector2i
				if to_data is Dictionary:
					to = Vector2i(to_data.get("x", 0), to_data.get("y", 0))
				else:
					to = Vector2i(to_data[0], to_data[1])
				if aid in _players and is_instance_valid(_players[aid]):
					if instant_mode:
						_players[aid].set_tile_position(to)
					else:
						_players[aid].move_to_tile(to)
				else:
					# Lazy spawn — covers logs where game_start lacks players array.
					# Spawn at the move's origin so the step animates correctly.
					var from_data = act.get("from", {})
					var spawn_tile: Vector2i = to
					if from_data is Dictionary:
						spawn_tile = Vector2i(from_data.get("x", 0), from_data.get("y", 0))
					_spawn_player_node(aid, pname, spawn_tile, aid % AGENT_COLORS.size())
				_record_action(aid, "move (%d,%d)" % [to.x, to.y])

			"say":
				var message: String = act.get("message", "")
				if message == "":
					continue
				var color_idx = _player_colors.get(aid, 0)
				var color_str = AGENT_COLORS[color_idx % AGENT_COLORS.size()]

				if aid in _players and is_instance_valid(_players[aid]):
					_players[aid].show_message(message)

				var bbcode = "[b][color=%s]%s[/color][/b]: %s" % [color_str, pname, message]
				chat_box.add_message(bbcode, ev.get("elapsed_ms", -1.0))
				_record_action(aid, "say: " + message)

			"attack":
				# Kill rendering is handled by the separate kill event.
				# The attack sub-action just notes who was targeted.
				var target = act.get("target", "")
				_record_action(aid, ("⚔ " + str(target)) if str(target) != "" else "⚔")

			"kill":
				# Victim becomes a visible corpse at their current tile
				var victim_name: String = str(act.get("victim", act.get("target", "")))
				if victim_name != "":
					for vid in _players.keys():
						if str(_player_names.get(vid, "")) == victim_name \
								and is_instance_valid(_players[vid]):
							_players[vid].set_dead()
							break
				_record_action(aid, "killed " + victim_name)

			"vote":
				_record_action(aid, "vote: " + str(act.get("voted_for", act.get("target", "?"))))

			"report":
				var rvictim: String = str(act.get("victim", act.get("target", "")))
				_record_action(aid, "report: " + rvictim)
				# The body is reported — remove the corpse from the world
				for vid in _players.keys():
					if str(_player_names.get(vid, "")) == rvictim \
							and is_instance_valid(_players[vid]):
						_players[vid].queue_free()
						_players.erase(vid)
						_player_names.erase(vid)
						_player_colors.erase(vid)
						break

			_:
				if not silent:
					print("[Renderer]   untracked sub-action: ", atype)

func _ev_vote_cast(ev: Dictionary):
	"""Handle a vote_cast event (may contain combined actions from log format)."""
	# Update the voting board for every vote action in the event
	var actions: Array = ev.get("actions", [])
	for act in actions:
		if act is Dictionary and act.get("type", "") == "vote":
			_voting_set_vote(
				str(act.get("voter", ev.get("voter", ""))),
				str(act.get("voted_for", act.get("target", "?"))))
	if actions.size() > 0:
		_ev_actions(ev)
		return

	# Legacy format — no-op (vote_cast is currently just informational).

func _ev_system_message(ev: Dictionary):
	var message: String = ev.get("message", "")
	if message == "":
		return
	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: " + message, ev.get("elapsed_ms", -1.0))
	print("[Renderer] SYSTEM: ", message)

# ── Voting ──

func _ev_voting_start(ev: Dictionary):
	var players = ev.get("active_agents", ev.get("active_agent_ids", []))
	var timeout = ev.get("timeout", 30)
	var names = []
	for aid in players:
		names.append(_player_names.get(int(aid), "?"))
	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Emergency meeting! " + str(names.size()) + " players voting (" + str(timeout) + "s)", ev.get("elapsed_ms", -1.0))
	print("[Renderer] Voting started — players: ", ", ".join(names))
	_set_game_state("VOTING — " + str(int(timeout)) + "s", Color(0.9, 0.62, 0.33))
	_voting_show(players, timeout)

func _ev_voting_result(ev: Dictionary):
	var tallies = ev.get("tallies", null)
	if tallies == null:
		tallies = ev.get("vote_tallies", {})
	var ejected = ev.get("ejected", "")
	var was_imposter = ev.get("was_imposter", false)

	# Build tally string — handles both dict format {name: count} and
	# array format ["name (count)", ...] from the log.
	var tally_str: String
	if tallies is Array:
		tally_str = ", ".join(tallies) if tallies.size() > 0 else "no votes cast"
	elif tallies is Dictionary and tallies.keys().size() > 0:
		var parts = []
		for target in tallies.keys():
			parts.append(str(target) + " (" + str(tallies[target]) + ")")
		tally_str = ", ".join(parts)
	else:
		tally_str = "no votes cast"

	# Hide the ejected player (log format includes agent_id)
	var aid = int(ev.get("agent_id", -1))
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].visible = false

	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Votes: " + tally_str, ev.get("elapsed_ms", -1.0))
	_voting_show_result(tally_str, str(ejected))
	if ejected != "":
		var imp_label = " (was imposter!)" if was_imposter else ""
		chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: " + str(ejected) + " was ejected!" + imp_label, ev.get("elapsed_ms", -1.0))
	else:
		chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: No ejection — tie or skip.", ev.get("elapsed_ms", -1.0))

# ── Camera ───────────────────────────────────────────────────────────────

func _update_camera(_delta):
	# Gather positions of all visible player nodes
	var positions: Array = []
	for aid in _players.keys():
		var node = _players[aid]
		if is_instance_valid(node) and node.visible:
			positions.append(node.global_position)

	if positions.size() == 0:
		return

	# Compute bounding box
	var min_pos = positions[0]
	var max_pos = positions[0]
	for pos in positions:
		min_pos.x = min(min_pos.x, pos.x)
		min_pos.y = min(min_pos.y, pos.y)
		max_pos.x = max(max_pos.x, pos.x)
		max_pos.y = max(max_pos.y, pos.y)

	# Add padding
	min_pos -= Vector2(_camera_padding, _camera_padding)
	max_pos += Vector2(_camera_padding, _camera_padding)

	# Enforce minimum world size
	var world_size = max_pos - min_pos
	world_size.x = max(world_size.x, _camera_min_world_size)
	world_size.y = max(world_size.y, _camera_min_world_size)

	# Target zoom
	var viewport_size = get_viewport().get_visible_rect().size
	if viewport_size.x == 0 or viewport_size.y == 0:
		return

	var target_zoom_x = viewport_size.x / world_size.x
	var target_zoom_y = viewport_size.y / world_size.y
	var target_zoom = min(target_zoom_x, target_zoom_y)
	target_zoom = clamp(target_zoom, _camera_min_zoom, _camera_max_zoom)

	# Center
	var target_pos = (min_pos + max_pos) / 2.0

	# Smooth interpolation (skip during instant_mode for snappy seek)
	if instant_mode:
		camera.global_position = target_pos
		camera.zoom = Vector2(target_zoom, target_zoom)
	else:
		var weight = clamp(_camera_smooth_speed * _delta, 0.0, 1.0)
		camera.global_position = camera.global_position.lerp(target_pos, weight)
		camera.zoom = camera.zoom.lerp(Vector2(target_zoom, target_zoom), weight)
