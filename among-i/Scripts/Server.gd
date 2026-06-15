# ServerManager.gd
extends Node

@export var player_scene: PackedScene = preload("res://Player.tscn")
@export var tile_map: TileMapLayer
@onready var chat_box = $ChatBox

var clients: Dictionary[int, GameClient] = {} # Dictionary to map Peer ID to Player Instance
var game_clients: Dictionary[int, GameClient] = {} # Dictionary to map Peer ID to Player Instance
var port := 8080

var KILL_DISTANCE = 2

var CHAT_DISTANCE = 10000

var start_time = 5
var max_game_length = 300
var min_players = 1
var imposters_count = 1

# Colors matching the 7 Among Us sprite columns (index 0–6)
var AGENT_COLORS = ["#C51111", "#132ED2", "#117F2D", "#ED54BB", "#EF7D0E", "#C8CD00", "#3F474E"]
var AGENT_NAMES = ["Red", "Blue", "Green", "Pink", "Orange", "Yellow", "Black", "White", "Purple", "Brown"]

enum State {WAITING_FOR_PLAYERS, STARTING, PLAYING}

# Server State
var game_state = State.WAITING_FOR_PLAYERS
var state_countdown = 0.0

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
	
func get_context_packet(agent_client):
	var client = clients.get(agent_client.id, null)
	if client == null:
		print("Received action for unknown client ID: ", agent_client.id)
		return

	var id = client.id
	var visibility_radius = 4 # Adjust this for a 5x5 grid (2*2 + 1)
	
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
		"is_imposter": client.is_imposter,
		"is_idle": client.is_active == false
	}

## Generates an ASCII representation of the tiles around a center point
func get_ascii_world_view(center_tile: Vector2i, radius: int) -> String:
	var ascii_grid = ""
	
	# 1. Define character mapping
	var mapping = {
		"walkable": ". ",
		"blocked": "# ",
		"player": "@ "
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
			dist = closest_distance
			closest_client = client2
			
	return closest_client
		
func kill_client(victim, killer):
	victim.is_active = false
	victim.node.visible = false
	game_clients.erase(victim.id)
	EventLogger.log_event("combat", "kill", {"victim": victim.name, "killer": killer.name})
	print(victim.name + " was killed by "+killer.name)
	
func handle_action(agent_client, response):
	var client = clients.get(agent_client.id, null)
	if client == null:
		print("Received action for unknown client ID: ", agent_client.id)
		return

	if client.is_active == false:
		return


	var player_node = client.node
	if response.has("move_x") and response.has("move_y"):
		var new_tile: Vector2i = client.tile + Vector2i(response.move_x, -response.move_y)
		
		if new_tile != client.tile:
			if player_node.move_to_tile(new_tile):
				print("Moved to", new_tile)
				client.tile = new_tile
				
	if response.has("attack") and client.is_imposter \
		and response["attack"].to_lower() == "attack":
		# Looking for closest player
		var closest_player = get_closest_client(client)
		if closest_player:
			kill_client(closest_player, client)
		
	
	if response.has("chat") and response.chat.strip_edges() != "":
		# print("chatted")
		var speech_bubble = player_node.get_node("SpeechBubble")
		var char_chat = speech_bubble.get_child(0)
		char_chat.text = response.chat
		speech_bubble.visible = response.chat != ""

		var chat_string = client.name + ": " + response.chat
		var color = AGENT_COLORS[client.index % AGENT_COLORS.size()]
		var bbcode_msg = "[b][color=%s]%s[/color][/b]: %s" % [color, client.name, response.chat]
		chat_box.add_message(bbcode_msg, chat_string)

		for id2 in game_clients:
			var client2 = game_clients[id2]
			if client_distance(client, client2) <= CHAT_DISTANCE and id2 != client.id:
				client2.chat_context.append(chat_string)
			
		
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
	var crewmates = 0 
	var imposters = 0

	for id in game_clients.keys():
		var client = game_clients[id]
		if client.is_imposter:
			imposters += 1
		else:
			crewmates += 1
	
	return (crewmates <= imposters and (crewmates+imposters) > 0) or state_countdown < 0

func set_starting_game():
	game_state = State.STARTING
	print("Game Starting Soon!")
	state_countdown = start_time
		
func end_game():
	print("Game Over!")
	for id in game_clients.keys():
		var client = game_clients[id]
		client.is_active = false

	set_starting_game()

func set_start_game():
	game_state = State.PLAYING
	state_countdown = max_game_length
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
		client.is_imposter = id in imposter_ids

func _ready():
	Agents.get_context_packet = get_context_packet
	Agents.handle_client_action = handle_action
	Agents.add_client = register_agent
	Agents.remove_client = remove_agent

func _process(_delta):
	state_countdown -= _delta

	# print("State Countdown: ", state_countdown)
	# print(len(clients), " clients connected.")

	if game_state == State.WAITING_FOR_PLAYERS and len(clients) >= min_players:
		print("Minimum players reached. Starting game soon!")
		set_starting_game()
	elif game_state == State.STARTING and state_countdown <= 0:
		set_start_game()
	elif game_state == State.PLAYING and game_end_condition():
		end_game()
