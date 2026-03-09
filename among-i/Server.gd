# ServerManager.gd
extends Node

@export var player_scene: PackedScene = preload("res://Player.tscn")

var server := TCPServer.new()
var clients := {} # Dictionary to map Peer ID to Player Instance
var port := 8080

var MIN_TIMESTEP = 3
var UPDATE_INTERVAL = 3.0 # Send data once per second


var CHAT_DISTANCE = 10000

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
	
func compress_chat_context(chat_context):
	# Ensure the array has at least 10 elements.
		# If the array has fewer than 10, it will return the entire array.
	if chat_context.size() <= 10:
		return chat_context.duplicate() # Return a copy of the whole array.
	#else:
		# Use slicing from the 10th-to-last element to the end.
		# The syntax [start_index:end_index] creates a new array.
		# Omitting the end_index goes to the end of the array.
		#return chat_context[-10:]
	
func get_context_packet(client):
	var id = client.id
	var player_node = client.node
	
	var other_bots = []
	for id2 in clients.keys():
		if id2 == id:
			continue

		other_bots.append(get_relative_client_data(client, clients[id2]))
	
	return {
		"id": id,
		"pos": {
			"x": round(player_node.position.x), 
			"y": round(player_node.position.y)
			},
		"bots": other_bots,
		"name": client.name,
		"chat_logs": client.chat_context.slice(-10)
	}
	
func handle_action(client, response):
	var player_node = client.node
	if response.has("move"):
		print("Moved")
		var character_body = player_node.get_child(0)
		character_body.move_agent(response.move)
	
	if response.has("chat"):
		print("chatted")
		var char_chat = player_node.get_child(1)
		char_chat.text = response.chat
		
		var chat_string = client.name + ": " + response.chat
		
		for id2 in clients:
			var client2 = clients[id2]
			if client_distance(client, client2) <= CHAT_DISTANCE:
				client2.chat_context.append(chat_string)
			
		
func add_client():
	var conn = server.take_connection()
	var socket = WebSocketPeer.new()
	socket.accept_stream(conn)
	
	# Create a unique ID for this client
	var client_id = socket.get_instance_id() 
	
	# Spawn a new player instance
	var new_player = player_scene.instantiate()
	new_player.name = "Agent_" + str(client_id)
	add_child(new_player)
	new_player.position = Vector2(randf_range(100, 500), randf_range(100, 500))
	
	# Store both the socket and the player node
	clients[client_id] = {
		"id": client_id,
		"socket": socket, 
		"node": new_player,
		"name": "undefined",
		"chat_context": [],
		"time_since_last_update": UPDATE_INTERVAL, # So it imediatly sends update
		"position": new_player.position
		}
	print("Spawned player for Client: ", client_id)

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
			print(packet)
			print(data)
			if not data:
				continue 
				
			if client.name == "undefined":
				client.name = data["name"]
				player.get_child(2).text = data["name"]
				
			handle_action(client, data)
			
		
		client.position = player.position
		
		# Send current state back to the specific Python agent
		
		
		if got_packet or client.time_since_last_update >= UPDATE_INTERVAL:
			
			var context = get_context_packet(client)
			socket.send_text(JSON.stringify(context))
			print("Sent Context")
			client.time_since_last_update = 0.0 # Reset the clock
		
		
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
	
		
