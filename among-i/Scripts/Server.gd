# ServerManager.gd
extends Node

@export var player_scene: PackedScene = preload("res://Player.tscn")
@export var tile_map: TileMapLayer
@onready var chat_box = $ChatBox
@onready var camera: Camera2D = $Camera2D

var clients: Dictionary[int, GameClient] = {} # Dictionary to map Peer ID to Player Instance
var game_clients: Dictionary[int, GameClient] = {} # Dictionary to map Peer ID to Player Instance
var port := 8080

var KILL_DISTANCE = 3

var CHAT_DISTANCE = 10000

# Camera auto-framing
var _camera_padding: float = 500.0
var _camera_min_zoom: float = 0.05
var _camera_max_zoom: float = 8.0
var _camera_smooth_speed: float = 4.0
var _camera_min_world_size: float = 400.0

var start_time = 15
var max_game_length = 600
var min_players = 1
var imposters_count = 1

# Colors matching the 7 Among Us sprite columns (index 0–6)
var AGENT_COLORS = ["#C51111", "#132ED2", "#117F2D", "#ED54BB", "#EF7D0E", "#C8CD00", "#3F474E"]
var AGENT_NAMES = ["Red", "Blue", "Green", "Pink", "Orange", "Yellow", "Black", "White", "Purple", "Brown"]

const BASE_PROMPT = """
You are a bot. Wander around and chat with other bots. Chat word limit is 10 per message.
You can move two tiles in the x and y directions each turn including diagonals, or choose to stay idle.
You can also respond to others or say something in chat. Provide your response in a structured format with 'move', 'chat', and 'reason' fields.
You are a 2D grid explorer. Your surroundings are represented by an ASCII grid where @ is You (always the center),
 . is Walkable ground, and # is a Wall or obstacle.
"""
const CREWMATE_INSTRUCTIONS = """
You are a crewmate. Stay alive, observe other bots, and chat naturally. Avoid attacking unless necessary.
"""
const IMPOSTOR_INSTRUCTIONS = """
You are an impostor. Your goal is to eliminate crewmates. When another bot is nearby
(within a few tiles), set attack to "attack" in your response to kill them.
Attack only when someone is close — the kill only works on the nearest bot within range.
Blend in by chatting normally and avoid drawing suspicion.
"""

const VOTE_PROMPT = """
VOTING PHASE: Discuss and then cast your vote.
You cannot move or attack during voting.
After 30 seconds the player with the most votes will be ejected.
"""

enum State {WAITING_FOR_PLAYERS, STARTING, PLAYING, VOTING}

# Server State
var game_state = State.WAITING_FOR_PLAYERS
var _state_timer = 0.0     # countdown for STARTING and VOTING phases
var _game_timer = 0.0      # countdown for PLAYING phase (game length)
var recent_global_chats: Array = []
var recent_events: Array = []
var vote_choices: Dictionary = {}
var _game_kills: int = 0
var _game_ejections: int = 0
var _phase_id: int = 0
var _last_vote_log_second: int = -1
var _clear_memory_flags: Dictionary = {}

func _bump_phase() -> void:
	_phase_id += 1
	Agents.force_send_all()

func broadcast_system_message(message: String) -> void:
	var bbcode = "[b][color=#FFFFFF]SYSTEM[/color][/b]: " + message
	chat_box.add_message(bbcode)
	recent_global_chats.append(message)
	print("SYSTEM: ", message)

func check_win_condition() -> Dictionary:
	var crewmates = 0
	var imposters = 0
	for id in game_clients.keys():
		var c = game_clients[id]
		if c.is_imposter:
			imposters += 1
		else:
			crewmates += 1
	var total = crewmates + imposters
	if imposters == 0 and total > 0:
		return {"game_over": true, "winner": "crewmates"}
	elif crewmates <= imposters and total > 0:
		return {"game_over": true, "winner": "imposters"}
	return {"game_over": false, "winner": ""}

func client_distance(client, client2):
	var client_pos = client.tile
	var client2_pos = client2.tile
	return client_pos.distance_to(client2_pos)

# Client2 from Client 1s perspective
func get_relative_client_data(client, client2):
	var client_pos = client.tile
	var client2_pos = client2.tile
	var diff = client2_pos - client_pos
	return {
		"distance": client_pos.distance_to(client2_pos),
		"delta_x":  diff.x,
		"delta_y":  -diff.y,
		"name": client2.name
	}
	
func build_prompt(client, world_view, chat_logs, bots, events=[]):
	var prompt = BASE_PROMPT
	prompt += "Your name is %s.\n" % client.name
	if client.first_time:
		prompt += "This is your first turn — introduce yourself!\n"
		client.first_time = false
	
	if client.is_imposter:
		prompt += IMPOSTOR_INSTRUCTIONS
	else:
		prompt += CREWMATE_INSTRUCTIONS
	
	# Recent game events
	if events.size() > 0:
		prompt += "\nRecent events:\n"
		for ev in events:
			var etype = ev.get("type", "")
			if etype == "kill":
				prompt += "- %s was killed! Witnesses: %s\n" % [ev.get("victim", "?"), str(ev.get("witnesses", []))]
			elif etype == "eject":
				prompt += "- %s was ejected by vote (was imposter: %s)\n" % [ev.get("victim", "?"), ev.get("was_imposter", false)]
			elif etype == "voting_started":
				prompt += "- Emergency meeting called! %d players voting.\n" % ev.get("players", 0)

	prompt += "Your current local map view is:\n%s\n" % world_view
	if chat_logs.size() > 0:
		prompt += "Here are the recent chats:\n"
		for chat_entry in chat_logs:
			prompt += "- %s\n" % chat_entry
	else:
		prompt += "There are no recent chat messages.\n"
	
	prompt += "The bots that are visible to you are:\n"
	if bots.size() == 0:
		prompt += "None\n"
	else:
		for bot in bots:
			prompt += "%s : %s, %s\n" % [bot.get("name", "Unknown"), bot.get("delta_x", 0), bot.get("delta_y", 0)]
	return prompt

func get_action_schema(client):
	if game_state == State.VOTING:
		return {
			"type": "object",
			"additionalProperties": false,
			"properties": {
				"vote": {"type": "string", "description": "Name to vote for or 'skip'"},
				"chat": {"type": "string", "description": "Chat message to broadcast during voting"}
			},
			"required": ["vote"]
		}
	else:
		var properties = {
			"move_x": {"type": "integer", "description": "How many steps to move horizontally: negative for left, 0 for idle, positive for right."},
			"move_y": {"type": "integer", "description": "How many steps to move vertically: negative for up, 0 for idle, positive for up."},
			"chat": {"type": "string", "description": "Chat message."},
			"reason": {"type": "string", "description": "Logic behind the move."}
		}
		if client.is_imposter:
			properties["attack"] = {"type": "string", "description": "Set to 'attack' to kill the nearest bot within range. Leave empty or omit otherwise."}
		return {
			"type": "object",
			"additionalProperties": false,
			"properties": properties,
			"required": ["move_x", "move_y", "chat", "reason"]
		}

	

func start_voting():
	print("══════════ VOTING STARTED ══════════")
	game_state = State.VOTING
	_state_timer = 30.0
	_bump_phase()
	vote_choices.clear()
	print("VOTING: %d active players must vote (30s timeout)" % game_clients.size())
	EventLogger.log_event("voting", "start", {"active_players": game_clients.size()})
	recent_events.append({"type": "voting_started", "players": game_clients.size()})

func eject_client(victim):
	if victim == null:
		return
	victim.is_active = false
	victim.node.visible = false
	if victim.id in game_clients:
		game_clients.erase(victim.id)
	EventLogger.log_event("voting", "eject", {"victim": victim.name})
	_game_ejections += 1
	recent_events.append({
		"type": "eject",
		"victim": victim.name,
		"was_imposter": victim.is_imposter,
	})
	print(victim.name + " was ejected by vote")

func tally_vote_totals() -> Dictionary:
	var totals: Dictionary = {}
	for voter_id in vote_choices.keys():
		var voted_name = vote_choices[voter_id]
		totals[voted_name] = totals.get(voted_name, 0) + 1
	return totals

func finalize_voting():
	# Guard against double-finalize (can be called from _process timer and handle_action early-end)
	if game_state != State.VOTING:
		return

	print("VOTING: Finalizing — %d votes cast, tallying..." % vote_choices.size())

	var totals = tally_vote_totals()

	# Announce vote counts
	var tally_strings: Array = []
	for vote_target in totals.keys():
		tally_strings.append("%s (%d)" % [vote_target, totals[vote_target]])
	if tally_strings.size() > 0:
		broadcast_system_message("Vote results: " + ", ".join(tally_strings))
	else:
		broadcast_system_message("No votes were cast.")

	if totals.size() == 0:
		print("No votes cast. Resuming game.")
		_bump_phase()
		game_state = State.PLAYING
		return

	var max_votes = 0
	var winners: Array = []
	for key_name in totals.keys():
		var count = totals[key_name]
		if count > max_votes:
			max_votes = count
			winners = [key_name]
		elif count == max_votes:
			winners.append(key_name)

	# Tie or skip handling
	if winners.size() != 1:
		broadcast_system_message("Vote tied. Nobody was ejected.")
		print("Vote tied or ambiguous. No ejection.")
		_bump_phase()
		game_state = State.PLAYING
		vote_choices.clear()
		return

	var voted_name = winners[0]
	if voted_name == "skip":
		broadcast_system_message("Players chose to skip. Nobody was ejected.")
		print("Players skipped voting. No ejection.")
		_bump_phase()
		game_state = State.PLAYING
		vote_choices.clear()
		return

	# Find the client with that name and eject them
	var victim = null
	for id in clients.keys():
		var c = clients[id]
		if c.name == voted_name:
			victim = c
			break

	if victim != null:
		eject_client(victim)
		broadcast_system_message(victim.name + " was ejected!")
		EventLogger.log_event("voting", "result", {"ejected": victim.name, "was_imposter": victim.is_imposter, "vote_tallies": tally_strings})

		# Check win condition after ejection
		var result = check_win_condition()
		if result.game_over:
			end_game(result.winner)
			vote_choices.clear()
			return
	else:
		print("Voted name not found among clients: ", voted_name)

	vote_choices.clear()
	_bump_phase()
	game_state = State.PLAYING
	print("══════════ VOTING ENDED — returning to PLAYING ══════════")

func get_context_packet(agent_client):
	var client = clients.get(agent_client.id, null)
	if client == null:
		print("Received action for unknown client ID: ", agent_client.id)
		return

	# Dead/inactive clients: send minimal idle context
	if not client.is_active:
		return {
			"id": client.id,
			"pos": {"x": client.tile.x, "y": client.tile.y},
			"name": client.name,
			"is_imposter": client.is_imposter,
			"is_idle": true,
			"prompt": "",
			"action_schema": {"type": "object", "additionalProperties": false, "properties": {}, "required": []},
			"bots": [],
			"chat_logs": [],
			"events": recent_events.duplicate(),
			"world_view": "",
			"phase_id": _phase_id,
		}

	var id = client.id
	var visibility_radius = 3  # 7x7 grid (compact — saves tokens vs 9x9)
	
	# 1. Fetch the tile neighborhood
	# Assuming 'tile_map' is accessible globally or on the server node
	var neighborhood = get_ascii_world_view(client.tile, visibility_radius)
	
	var other_bots = []
	for id2 in game_clients.keys():
		if id2 == id:
			continue
		var packet = get_relative_client_data(client, game_clients[id2])
		
		# Checking Visibility range
		if abs(packet.delta_x) <= visibility_radius \
			and abs(packet.delta_y) <= visibility_radius:
			other_bots.append(packet)
	
	var chat_context = client.chat_context
	client.chat_context = []

	# Keep events list bounded and snapshot for this agent
	if recent_events.size() > 50:
		recent_events = recent_events.slice(recent_events.size() - 50, recent_events.size())
	var events_snapshot = recent_events.duplicate()

	# Prepare defaults
	var prompt = ""
	var action_schema = {}

	# Voting phase: broadcast all chats to everyone and provide voting schema
	if game_state == State.VOTING:
		# Near timeout — don't waste tokens, agent won't have time to respond
		if _state_timer < 5.0:
			return {
				"id": id,
				"pos": {"x": client.tile.x, "y": client.tile.y},
				"name": client.name,
				"bots": [],
				"world_view": "",
				"chat_logs": [],
				"events": events_snapshot,
				"prompt": "Voting almost over. Wait for results.",
				"is_imposter": client.is_imposter,
				"is_idle": false,
				"action_schema": {"type": "object", "additionalProperties": false, "properties": {}, "required": []},
				"clear_memory": false,
				"phase_id": _phase_id,
			}

		# Use recent global chats for context (last 50)
		var start_idx = max(0, recent_global_chats.size() - 50)
		chat_context = recent_global_chats.slice(start_idx, recent_global_chats.size())

		# Build a voting-specific prompt (only active players)
		var player_names: Array = []
		for idn in game_clients.keys():
			player_names.append(game_clients[idn].name)

		
		var vote_prompt = VOTE_PROMPT
		if events_snapshot.size() > 0:
			vote_prompt += "\nRecent events:\n"
			for ev in events_snapshot:
				var etype = ev.get("type", "")
				if etype == "kill":
					vote_prompt += "- %s was killed!\n" % ev.get("victim", "?")
				elif etype == "eject":
					vote_prompt += "- %s was ejected (was imposter: %s)\n" % [ev.get("victim", "?"), ev.get("was_imposter", false)]
		vote_prompt += "Players: %s\n" % String(", ").join(player_names)
		vote_prompt += "Recent global chats:\n"
		for c in chat_context:
			vote_prompt += "- %s\n" % c

		vote_prompt += "Current votes:\n"
		for voter_id in vote_choices.keys():
			var voter_name = "Unknown"
			if voter_id in clients:
				voter_name = clients[voter_id].name
			vote_prompt += "%s -> %s\n" % [voter_name, vote_choices[voter_id]]

		prompt = vote_prompt

		action_schema = {
			"type": "object",
			"additionalProperties": false,
			"properties": {
				"vote": {"type": "string", "description": "Name to vote for or 'skip'"},
				"chat": {"type": "string", "description": "Chat message to broadcast during voting"}
			},
			"required": ["vote"]
		}
	else:
		prompt = build_prompt(client, neighborhood, chat_context, other_bots, events_snapshot)
		action_schema = get_action_schema(client)
	
	var clear_mem = _clear_memory_flags.get(id, false)
	if clear_mem:
		_clear_memory_flags[id] = false

	return {
		"id": id,
		"pos": {
			"x": client.tile.x,
			"y": client.tile.y
		},
		"name": client.name,
		"bots": other_bots,
		"world_view": neighborhood, # Ascii ART
		"chat_logs": chat_context,
		"events": events_snapshot,
		"prompt": prompt,
		"is_imposter": client.is_imposter,
		"is_idle": client.is_active == false,
		"action_schema": action_schema,
		"clear_memory": clear_mem,
		"phase_id": _phase_id,
	}

## Generates an ASCII representation of the tiles around a center point
func get_ascii_world_view(center_tile: Vector2i, radius: int) -> String:
	var ascii_grid = ""
	
	# 1. Define character mapping (compact — no space padding, saves tokens)
	var mapping = {
		"walkable": ".",
		"blocked": "#",
		"player": "@"
	}

	# 2. Iterate through the neighborhood
	for y in range(-radius, radius + 1):
		var line = ""
		for x in range(-radius, radius + 1):
			# The player is always at the relative (0,0) offset
			if x == 0 and y == 0:
				line += mapping["player"]
				continue
			
			var target_coords = center_tile + Vector2i(x, y)
			var data = tile_map.get_cell_tile_data(target_coords)
			var is_walkable = false
			
			# Check if tile exists and if the "walkable" custom data is true
			if data:
				is_walkable = data.get_custom_data("walkable")
			
			# 3. Append character based on walkability
			if is_walkable:
				line += mapping["walkable"]
			else:
				line += mapping["blocked"]
		
		# Add the completed row to the final string with a newline
		ascii_grid += line + "\n"
	
	return ascii_grid

	
func get_closest_client(client):
	var closest_client = null 
	var closest_distance = 10000000
	for id in game_clients.keys():
		var client2 = game_clients[id]
		if id == client.id:
			continue
		
		var dist = client_distance(client, client2)
		# print("Distance:", dist)
		if dist < closest_distance and dist < KILL_DISTANCE:
			closest_distance = dist
			closest_client = client2
			
	return closest_client
		
func kill_client(victim, killer):
	victim.is_active = false
	victim.node.visible = false
	game_clients.erase(victim.id)

	# Collect witnesses — agents within chat distance of the victim
	var witnesses: Array = []
	for id in game_clients.keys():
		var c = game_clients[id]
		if c.id != victim.id and c.id != killer.id:
			if client_distance(victim, c) <= CHAT_DISTANCE:
				witnesses.append(c.name)

	EventLogger.log_event("combat", "kill", {
		"victim": victim.name,
		"killer": killer.name,
		"witnesses": witnesses,
	})
	_game_kills += 1
	recent_events.append({
		"type": "kill",
		"victim": victim.name,
		"witnesses": witnesses,
	})
	print(victim.name + " was killed by " + killer.name + " — witnesses: " + str(witnesses))

	# Check if the kill ends the game
	var result = check_win_condition()
	if result.game_over:
		end_game(result.winner)
		return

	# Trigger body-report meeting
	broadcast_system_message(victim.name + " was found dead! Starting emergency meeting...")
	start_voting()

func handle_chat(client, message, broadcast=false):
	message= message.strip_edges()
	var player_node = client.node
	var speech_bubble = player_node.get_node("SpeechBubble")
	var char_chat = speech_bubble.get_child(0)
	char_chat.text = message
	speech_bubble.visible = message != ""

	if message == "":
		return

	var chat_string = client.name + ": " + message
	var color = AGENT_COLORS[client.index % AGENT_COLORS.size()]
	var bbcode_msg = "[b][color=%s]%s[/color][/b]: %s" % [color, client.name, message]
	chat_box.add_message(bbcode_msg)
	recent_global_chats.append(chat_string)
	EventLogger.log_event("chat", "say", {
		"actor": client.name,
		"message": message,
		"broadcast": broadcast,
		"pos": {"x": client.tile.x, "y": client.tile.y},
	})

	for id2 in game_clients:
		if id2 == client.id:
			continue

		var client2 = game_clients[id2]
		var in_distance = client_distance(client, client2) <= CHAT_DISTANCE
		if in_distance or broadcast:
			client2.chat_context.append(chat_string)
	
func handle_action(agent_client, response):
	var client = clients.get(agent_client.id, null)
	if client == null:
		print("Received action for unknown client ID: ", agent_client.id)
		return

	if client.is_active == false:
		return

	# Void stale responses from a previous phase
	if response.has("phase_id") and response["phase_id"] != _phase_id:
		print("Voiding stale response from ", client.name, " (phase ", response["phase_id"], " != ", _phase_id, ")")
		return

	var player_node = client.node

	# If we're in voting phase, disallow movement/attacks and handle votes/chat broadcasts
	if game_state == State.VOTING:
		if response.has("vote"):
			var voted_name = ""
			if typeof(response.vote) == TYPE_STRING:
				voted_name = response.vote
			elif response.has("vote"):
				voted_name = str(response["vote"])
			if voted_name == "":
				voted_name = "skip"

			vote_choices[client.id] = voted_name
			print("VOTING: %s -> %s  (%d/%d votes)" % [client.name, voted_name, vote_choices.size(), game_clients.size()])
			EventLogger.log_event("voting", "vote_cast", {"voter": client.name, "voted_for": voted_name, "votes_so_far": vote_choices.size(), "total_players": game_clients.size()})

			# Early end: if all active players have voted, finalize immediately
			if vote_choices.size() >= game_clients.size():
				print("VOTING: All %d players voted — finalizing early!" % game_clients.size())
				finalize_voting()

		handle_chat(client, response.chat, true) # Broadcast chat to all during voting

		# During voting, ignore movement/attack
		return
	if response.has("move_x") and response.has("move_y"):
		var new_tile: Vector2i = client.tile + Vector2i(response.move_x, -response.move_y)
		
		if new_tile != client.tile:
			if player_node.move_to_tile(new_tile):
				print("Moved to", new_tile)
				EventLogger.log_event("movement", "move", {
					"actor": client.name,
					"from": {"x": client.tile.x, "y": client.tile.y},
					"to": {"x": new_tile.x, "y": new_tile.y},
				})
				client.tile = new_tile
				
	if response.has("attack") and client.is_imposter \
		and response["attack"].to_lower() != "" \
		and response["attack"].to_lower() != "none":
		# Looking for closest player
		var closest_player = get_closest_client(client)
		if closest_player:
			kill_client(closest_player, client)
		
	
	handle_chat(client, response.chat)
			
		
func register_agent(agent_client):
	var client_id = agent_client.id

	var new_player = player_scene.instantiate()
	new_player.name = "Agent_%s" % client_id
	new_player.tile_map = tile_map
	add_child(new_player)
	var start_pos = Vector2i(randi_range(0, 5), randi_range(0, 5))
	new_player.set_tile_position(start_pos)

	var color_index = agent_client.index % AGENT_COLORS.size()
	var _name = AGENT_NAMES[agent_client.index % AGENT_NAMES.size()]
	new_player.get_node("Sprite2D").frame_coords = Vector2i(0, 0)
	new_player.get_node("Sprite2D").modulate = Color(AGENT_COLORS[color_index])

	# Store both the socket and the player node
	var client = GameClient.new(client_id, new_player, agent_client.index)
	client.name = _name
	client.tile = start_pos
	clients[client_id]  = client
	print("Spawned player for Client: ", client_id, " name=", client.name)

func remove_agent(agent_client):
	if agent_client.id in clients:
		var client = clients[agent_client.id]
		client.node.queue_free() # Remove the player node from the scene
		clients.erase(agent_client.id) # Remove from clients dictionary
		print("Removed player for Client: ", agent_client.id)


func game_end_condition():
	# Timer-based end
	if _game_timer <= 0:
		return true
	# Player-count-based end (all crewmates dead)
	if game_clients.size() == 0:
		return false
	var crewmates = 0
	for id in game_clients.keys():
		if not game_clients[id].is_imposter:
			crewmates += 1
	return crewmates <= 0

func set_starting_game():
	game_state = State.STARTING
	print("Game Starting Soon!")
	_state_timer = start_time
	_bump_phase()
		
func end_game(reason: String = ""):
	if reason == "crewmates":
		broadcast_system_message("Game Over! Crewmates win — all imposters eliminated!")
	elif reason == "imposters":
		broadcast_system_message("Game Over! Imposters win — all crewmates eliminated!")
	elif reason == "timeout":
		broadcast_system_message("Game Over! Time limit reached.")
	else:
		broadcast_system_message("Game Over! " + reason)
	print("Game Over! Reason: ", reason if reason != "" else "unknown")

	# Build player list with roles
	var players: Array = []
	for id in clients.keys():
		var c = clients[id]
		players.append({
			"name": c.name,
			"imposter": c.is_imposter,
			"alive": c.is_active,
		})

	var recap := {
		"winner": reason,
		"kills": _game_kills,
		"ejections": _game_ejections,
		"players": players,
	}

	for id in game_clients.keys():
		var client = game_clients[id]
		client.is_active = false

	EventLogger.end_game(recap)
	set_starting_game()

func set_start_game():
	if clients.size() == 0:
		return
	game_state = State.PLAYING
	_game_timer = max_game_length
	recent_events.clear()
	_game_kills = 0
	_game_ejections = 0
	_bump_phase()
	EventLogger.start_game()
	print("Game Starting!")

	# Randomly assign imposters
	var imposter_ids = []
	while len(imposter_ids) < imposters_count:
		var keys = clients.keys()
		var rand_id = keys[randi() % keys.size()]
		if rand_id not in imposter_ids:
			imposter_ids.append(rand_id)

	for id in clients.keys():
		var client = clients[id]
		game_clients[id] = client
		client.is_active = true
		client.node.visible = true
		# Randomize spawn position each game
		var spawn_tile = Vector2i(randi_range(1, 16), randi_range(1, 16))
		client.tile = spawn_tile
		client.node.set_tile_position(spawn_tile)
		client.is_imposter = id in imposter_ids
		_clear_memory_flags[id] = true

func _update_camera(_delta):
	# Gather world positions of all visible, active player nodes
	var positions: Array = []
	for id in game_clients.keys():
		var c = game_clients[id]
		if c.is_active and is_instance_valid(c.node) and c.node.visible:
			positions.append(c.node.global_position)
	# Also check any non-game_clients with visible nodes (e.g. recently killed, pre-restart)
	for id in clients.keys():
		var c = clients[id]
		if not id in game_clients and is_instance_valid(c.node) and c.node.visible:
			positions.append(c.node.global_position)

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

	# Enforce minimum world size so camera doesn't zoom in too far
	var world_size = max_pos - min_pos
	world_size.x = max(world_size.x, _camera_min_world_size)
	world_size.y = max(world_size.y, _camera_min_world_size)

	# Calculate target zoom to fit the world bounds in the viewport
	var viewport_size = get_viewport().get_visible_rect().size
	if viewport_size.x == 0 or viewport_size.y == 0:
		return

	var target_zoom_x = viewport_size.x / world_size.x
	var target_zoom_y = viewport_size.y / world_size.y
	var target_zoom = min(target_zoom_x, target_zoom_y)
	target_zoom = clamp(target_zoom, _camera_min_zoom, _camera_max_zoom)

	# Center of the bounding box
	var target_pos = (min_pos + max_pos) / 2.0

	# Smoothly interpolate position and zoom
	var weight = clamp(_camera_smooth_speed * _delta, 0.0, 1.0)
	camera.global_position = camera.global_position.lerp(target_pos, weight)
	camera.zoom = camera.zoom.lerp(Vector2(target_zoom, target_zoom), weight)

func _ready():
	Agents.get_context_packet = get_context_packet
	Agents.handle_client_action = handle_action
	Agents.add_client = register_agent
	Agents.remove_client = remove_agent

func _process(_delta):
	# Decrement the appropriate timer based on game state
	if game_state == State.PLAYING:
		_game_timer -= _delta
	elif game_state == State.STARTING or game_state == State.VOTING:
		_state_timer -= _delta

	_update_camera(_delta)

	if game_state == State.WAITING_FOR_PLAYERS and len(clients) >= min_players:
		print("Minimum players reached. Starting game soon!")
		set_starting_game()
	elif game_state == State.STARTING and _state_timer <= 0:
		set_start_game()
	elif game_state == State.PLAYING and game_end_condition():
		var result = check_win_condition()
		var reason = "timeout" if _game_timer <= 0 else result.winner
		if result.game_over:
			end_game(result.winner)
		else:
			end_game(reason)
	elif game_state == State.VOTING:
		if _state_timer <= 0:
			finalize_voting()
		else:
			var sec = int(_state_timer)
			if sec != _last_vote_log_second and sec % 10 == 0:
				print("VOTING: %.0fs remaining, %d/%d votes cast" % [_state_timer, vote_choices.size(), game_clients.size()])
			_last_vote_log_second = sec
