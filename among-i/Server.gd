# ServerManager.gd
extends Node

@export var player_scene: PackedScene = preload("res://Player.tscn")
@export var tile_map: TileMapLayer
@onready var chat_box = $ChatBox

var server := TCPServer.new()
var clients := {} # Dictionary to map Peer ID to Player Instance
var port := 8080

var MIN_TIMESTEP = 3
var UPDATE_INTERVAL = 3.0 # Send data once per second

var total_bots = 0

var CHAT_DISTANCE = 10000

# Colors matching the 7 Among Us sprite columns (index 0–6)
var AGENT_COLORS = ["#C51111", "#132ED2", "#117F2D", "#ED54BB", "#EF7D0E", "#C8CD00", "#3F474E"]

func _ready():
	if server.listen(port) == OK:
		print("Server listening for agents on port ", port)

func client_distance(client, client2):
	return client.node.position.distance_to(client2.node.position)

# Client2 from Client 1s perspective
func get_relative_client_data(client, client2):
	var client_pos = client.node.position
	var client2_pos = client2.node.position
	return {
		"distance": client_pos.distance_to(client2_pos),
		"angle":  client_pos.angle_to(client2_pos)
	}
	
func get_context_packet(client):
	var id = client.id
	var player_node = client.node
	var visibility_radius = 4 # Adjust this for a 5x5 grid (2*2 + 1)
	
	# 1. Fetch the tile neighborhood
	# Assuming 'tile_map' is accessible globally or on the server node
	var neighborhood = get_tile_neighborhood(client.tile, visibility_radius)
	
	var other_bots = []
	for id2 in clients.keys():
		if id2 == id:
			continue
		other_bots.append(get_relative_client_data(client, clients[id2]))
	
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
		"world_view": neighborhood, # The new 2D array of tile data
		"chat_logs": chat_context
	}
	
	

## Helper to build the JSON-friendly 2D array
func get_tile_neighborhood(center_tile: Vector2i, radius: int) -> Array:
	var grid = []
	
	for y in range(-radius, radius + 1):
		var row = []
		for x in range(-radius, radius + 1):
			var target_coords = center_tile + Vector2i(x, y)
			var data = tile_map.get_cell_tile_data(target_coords)
			var atlas_pos = tile_map.get_cell_atlas_coords(target_coords)
			
			# We build a dictionary that Python can easily parse
			var tile_info = {
				"x": target_coords.x,
				"y": target_coords.y,
				"type": "empty",
				"walkable": false
			}
			
			if tile_map.get_cell_source_id(target_coords) != -1:
				tile_info["type"] = str(atlas_pos) # e.g. "(1, 2)"
				if data:
					# Pull whatever custom data your Python bot needs to know
					tile_info["walkable"] = data.get_custom_data("walkable")
			
			row.append(tile_info)
		grid.append(row)
		
	return grid
	
func handle_action(client, response):
	var player_node = client.node
	if response.has("move_x") and response.has("move_y"):
		print("Moved")
		var new_tile: Vector2i = client.tile + Vector2i(response.move_x, response.move_y)
		
		if new_tile != client.tile:
			if player_node.move_to_tile(client.tile):
				client.tile = new_tile
	
	if response.has("chat"):
		print("chatted")
		var speech_bubble = player_node.get_node("SpeechBubble")
		var char_chat = speech_bubble.get_child(0)
		char_chat.text = response.chat
		speech_bubble.visible = response.chat != ""

		var chat_string = client.name + ": " + response.chat
		var color = AGENT_COLORS[client.color_index]
		var bbcode_msg = "[b][color=%s]%s[/color][/b]: %s" % [color, client.name, response.chat]
		chat_box.add_message(bbcode_msg, chat_string)

		for id2 in clients:
			var client2 = clients[id2]
			if client_distance(client, client2) <= CHAT_DISTANCE and id2 != client.id:
				client2.chat_context.append(chat_string)
			
		
func add_client():
	total_bots += 1
	var conn = server.take_connection()
	var socket = WebSocketPeer.new()
	socket.accept_stream(conn)
	
	# Create a unique ID for this client
	var client_id = socket.get_instance_id() 
	
	# Spawn a new player instance
	var new_player = player_scene.instantiate()
	new_player.name = "Agent_" + str(client_id)
	new_player.tile_map = tile_map
	add_child(new_player)
	new_player.position = Vector2(randf_range(100, 500), randf_range(100, 500))
	
	var color_index = total_bots % 7
	new_player.get_node("Sprite2D").frame_coords = Vector2i(color_index, 0)

	# Store both the socket and the player node
	clients[client_id] = {
		"id": client_id,
		"socket": socket,
		"node": new_player,
		"name": "undefined",
		"color_index": color_index,
		"first_time": true,
		"chat_context": [],
		"tile": Vector2i(0,0),
		"time_since_last_update": UPDATE_INTERVAL, # So it imediatly sends update
		"position": new_player.position
		}
	print("Spawned player for Client: ", client_id)

func send_client_context(socket, client):
	var context = get_context_packet(client)
	socket.send_text(JSON.stringify(context))
	print("Sent Context")
	client.time_since_last_update = 0.0 # Reset the clock

func update_client(client, _delta):	
	var socket = client.socket
	var player = client.node
	
	client.time_since_last_update += _delta
	
	socket.poll()
	var state = socket.get_ready_state()
	
	if state == WebSocketPeer.STATE_OPEN:
		# Receive commands from Python
		var got_packet = false
		while socket.get_available_packet_count() > 0:
			got_packet = true
			print("Recieved Player Packet")
			var packet = socket.get_packet().get_string_from_utf8()
			var data = JSON.parse_string(packet)
			print(data)
			if not data:
				continue 
				
			if client.name == "undefined":
				client.name = data.get("name", "UnknownBot")
				player.get_node("NameLabel").text = client.name
				
			handle_action(client, data)
			
		
		client.position = player.position
		
		# Send current state back to the specific Python agent
		
		
		if got_packet or client.first_time: # or client.time_since_last_update >= UPDATE_INTERVAL:
			send_client_context(socket, client)
			client.first_time = false
		
		
	elif state == WebSocketPeer.STATE_CLOSED:
		print("Client disconnected. Removing player.")
		player.queue_free()
		clients.erase(client.id)

func _process(_delta):
	# 1. Accept new connections
	if server.is_connection_available():
		add_client()
	
	# 2. Update all connected clients
	for id in clients.keys():
		update_client(clients[id], _delta)
