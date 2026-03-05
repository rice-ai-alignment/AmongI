# ServerManager.gd
extends Node

@export var player_scene: PackedScene = preload("res://Player.tscn")

var server := TCPServer.new()
var clients := {} # Dictionary to map Peer ID to Player Instance
var port := 8080

func _ready():
	if server.listen(port) == OK:
		print("Server listening for agents on port ", port)

func _process(_delta):
	# 1. Accept new connections
	if server.is_connection_available():
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
		clients[client_id] = {"socket": socket, "node": new_player}
		print("Spawned player for Client: ", client_id)

	# 2. Update all connected clients
	for id in clients.keys():
		var client = clients[id]
		var socket = client.socket
		var player = client.node
		
		socket.poll()
		var state = socket.get_ready_state()
		
		if state == WebSocketPeer.STATE_OPEN:
			# Receive commands from Python
			while socket.get_available_packet_count() > 0:
				print("Recieved Player Packet")
				var packet = socket.get_packet().get_string_from_utf8()
				var data = JSON.parse_string(packet)
				if data and data.has("move"):
					var character_body = player.get_child(0)
					character_body.move_agent(data.move)
			
			# Send current state back to the specific Python agent
			var game_state = {
				"id": id,
				"pos": {"x": player.position.x, "y": player.position.y},
				"health": 100
			}
			socket.send_text(JSON.stringify(game_state))
			
			
		elif state == WebSocketPeer.STATE_CLOSED:
			print("Client disconnected. Removing player.")
			player.queue_free()
			clients.erase(id)
