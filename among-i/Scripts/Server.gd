# Server.gd — Pure renderer for the Among-I simulation.
# Receives render events from the Python game engine via WebSocket (port 8081)
# and drives the visual presentation: player sprites, movement animation,
# chat HUD, camera auto-framing.
#
# All game logic lives in engine.py. Godot only renders.

extends Node

@export var player_scene: PackedScene = preload("res://Player.tscn")
@export var tile_map: TileMapLayer
@onready var chat_box = $ChatBox
@onready var camera: Camera2D = $Camera2D

# ── Render WebSocket ─────────────────────────────────────────────────────

var _server := TCPServer.new()
var _render_port := 8081
var _render_peer: WebSocketPeer = null
var _peer_id: int = -1

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

# ── Camera auto-framing ──────────────────────────────────────────────────

var _camera_padding: float = 500.0
var _camera_min_zoom: float = 0.05
var _camera_max_zoom: float = 8.0
var _camera_smooth_speed: float = 4.0
var _camera_min_world_size: float = 400.0

# ── Chat ─────────────────────────────────────────────────────────────────

const MAX_CHAT_MESSAGES = 50

# ── Initialization ───────────────────────────────────────────────────────

func _ready():
	var err = _server.listen(_render_port)
	if err == OK:
		print("[Renderer] Listening for engine on port ", _render_port)
	else:
		print("[Renderer] FATAL: Cannot bind port ", _render_port, " (error ", err, ")")
		print("[Renderer] Is another Godot instance or process using this port?")
		get_tree().quit(1)

# ── Main loop ────────────────────────────────────────────────────────────

func _process(_delta):
	_accept_connection()
	_poll_render_peer()
	_update_camera(_delta)

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
		print("[Renderer] Python engine disconnected")
		_render_peer = null
		_peer_id = -1

# ── Event dispatcher ─────────────────────────────────────────────────────

func _handle_event(event: Dictionary):
	var etype: String = event.get("type", "")
	if etype not in ["", "heartbeat"]:
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

		_:
			print("[Renderer] Unknown event type: ", etype)

# ── Event handlers ───────────────────────────────────────────────────────

func _ev_game_start(ev: Dictionary):
	_clear_all_players()
	_game_active = true

	for pdata in ev.get("players", []):
		_spawn_player_node(
			pdata.get("agent_id", -1),
			pdata.get("name", "?"),
			Vector2i(pdata.get("tile", [0, 0])[0],
					 pdata.get("tile", [0, 0])[1]),
			pdata.get("color_index", 0)
		)
	# Already done by the chage state thing
	var gid = ev.get("game_id", "?")
	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Game started! (" + str(gid) + ")")

func _ev_game_end(ev: Dictionary):
	_game_active = false
	var winner = ev.get("winner", "?")
	var recap = ev.get("recap", {})
	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Game Over! " + str(winner) + " win!")
	print("[Renderer] Game ended — winner: ", winner, " recap: ", recap)

func _ev_phase_change(ev: Dictionary):
	var phase = ev.get("phase", "?")
	var countdown = ev.get("countdown_sec", 0)
	match phase:
		"starting":
			chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Game starting in " + str(int(countdown)) + "s...")
		"voting":
			chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: ══════ VOTING PHASE (" + str(int(countdown)) + "s) ══════")
		"playing":
			chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Playing!")

# ── Player spawn / despawn ──

func _ev_spawn_player(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	var name = ev.get("name", "?")
	var tile = Vector2i(ev.get("tile", [0, 0])[0], ev.get("tile", [0, 0])[1])
	var color_idx = ev.get("color_index", 0)
	_spawn_player_node(aid, name, tile, color_idx)

func _spawn_player_node(aid: int, pname: String, tile: Vector2i, color_idx: int):
	# Remove existing node if re-spawning
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].queue_free()

	var player = player_scene.instantiate()
	player.name = "Agent_%d" % aid
	player.tile_map = tile_map
	add_child(player)
	player.set_tile_position(tile)

	# Set sprite color
	var color_str = AGENT_COLORS[color_idx % AGENT_COLORS.size()]
	player.get_node("Sprite2D").modulate = Color(color_str)

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
		_players[aid].move_to_tile(to)

# ── Player death / ejection / respawn ──

func _ev_player_died(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	var cause = ev.get("cause", "kill")
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].visible = false
		print("[Renderer] Player ", _player_names.get(aid, "?"), " died (", cause, ")")

func _ev_player_ejected(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].visible = false
		print("[Renderer] Player ", _player_names.get(aid, "?"), " ejected")

func _ev_player_respawn(ev: Dictionary):
	var aid = int(ev.get("agent_id", -1))
	var tile = Vector2i(ev.get("tile", [0, 0])[0], ev.get("tile", [0, 0])[1])
	if aid in _players and is_instance_valid(_players[aid]):
		_players[aid].visible = true
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

	# Show speech bubble on player node
	if aid in _players and is_instance_valid(_players[aid]):
		var player_node = _players[aid]
		var speech_bubble = player_node.get_node("SpeechBubble")
		if speech_bubble:
			var label = speech_bubble.get_child(0)
			label.text = message
			speech_bubble.visible = true

	# Add to chat HUD
	var bbcode = "[b][color=%s]%s[/color][/b]: %s" % [color_str, pname, message]
	chat_box.add_message(bbcode)

# ── Combined per-agent actions ────────────────────────────────────────

func _ev_actions(ev: Dictionary):
	"""Handle a combined actions event (log format: one event per agent per tick)."""
	var aid = int(ev.get("agent_id", -1))
	var pname = ev.get("actor", _player_names.get(aid, "?"))
	var actions: Array = ev.get("actions", [])
	print("[Renderer] _ev_actions: agent=", aid, " pname=", pname, " actions=", actions.size())

	for act in actions:
		var atype: String = act.get("type", "")
		print("[Renderer]   sub-action: ", atype, " act=", act)
		match atype:
			"move":
				if aid in _players and is_instance_valid(_players[aid]):
					var to_data = act.get("to", {})
					var to: Vector2i
					if to_data is Dictionary:
						to = Vector2i(to_data.get("x", 0), to_data.get("y", 0))
					else:
						to = Vector2i(to_data[0], to_data[1])
					print("[Renderer]   move player ", aid, " to ", to)
					_players[aid].move_to_tile(to)
				else:
					print("[Renderer]   player ", aid, " not found in _players: ", _players.keys())

			"say":
				var message: String = act.get("message", "")
				if message == "":
					continue
				var color_idx = _player_colors.get(aid, 0)
				var color_str = AGENT_COLORS[color_idx % AGENT_COLORS.size()]

				if aid in _players and is_instance_valid(_players[aid]):
					var player_node = _players[aid]
					var speech_bubble = player_node.get_node("SpeechBubble")
					if speech_bubble:
						var label = speech_bubble.get_child(0)
						label.text = message
						speech_bubble.visible = true

				var bbcode = "[b][color=%s]%s[/color][/b]: %s" % [color_str, pname, message]
				chat_box.add_message(bbcode)

			"attack":
				# Kill rendering is handled by the separate kill event.
				# The attack sub-action just notes who was targeted.
				pass

func _ev_vote_cast(ev: Dictionary):
	"""Handle a vote_cast event (may contain combined actions from log format)."""
	# The log format nests vote+chat in an actions array.
	var actions: Array = ev.get("actions", [])
	if actions.size() > 0:
		_ev_actions(ev)
		return

	# Legacy format — no-op (vote_cast is currently just informational).

func _ev_system_message(ev: Dictionary):
	var message: String = ev.get("message", "")
	if message == "":
		return
	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: " + message)
	print("[Renderer] SYSTEM: ", message)

# ── Voting ──

func _ev_voting_start(ev: Dictionary):
	var players = ev.get("active_agents", ev.get("active_agent_ids", []))
	var timeout = ev.get("timeout", 30)
	var names = []
	for aid in players:
		names.append(_player_names.get(aid, "?"))
	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Emergency meeting! " + str(names.size()) + " players voting (" + str(timeout) + "s)")
	print("[Renderer] Voting started — players: ", ", ".join(names))

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

	chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: Votes: " + tally_str)
	if ejected != "":
		var imp_label = " (was imposter!)" if was_imposter else ""
		chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: " + str(ejected) + " was ejected!" + imp_label)
	else:
		chat_box.add_message("[b][color=#FFFFFF]SYSTEM[/color][/b]: No ejection — tie or skip.")

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

	# Smooth interpolation
	var weight = clamp(_camera_smooth_speed * _delta, 0.0, 1.0)
	camera.global_position = camera.global_position.lerp(target_pos, weight)
	camera.zoom = camera.zoom.lerp(Vector2(target_zoom, target_zoom), weight)
