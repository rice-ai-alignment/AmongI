# EventLogger.gd — Autoload this as "EventLogger"
# Add to Project > Project Settings > Autoload

# Agents.gd
extends Node

const VERSION = "1.0"

var server := TCPServer.new()
var clients: Dictionary[int, AgentClient] = {} # Dictionary to map Peer ID to Player Instance
var port := 8080

var MIN_TIMESTEP = 3
var UPDATE_INTERVAL = 10.0 # Send data once per second

var total_bots = 0

	
var get_context_packet: Callable
var handle_client_action: Callable

var add_client: Callable
var remove_client: Callable

class AgentClient:
	var id: int
	var socket: WebSocketPeer
	var index: int = 0

	# Timing for updates
	var time_since_last_update: float = 0.0
	var first_time: bool = true

	func _init(_id, _socket, index):
		self.id = _id
		self.socket = _socket
		self.index = index
		

			


func update_client(client, _delta):	
	var socket = client.socket
	
	client.time_since_last_update += _delta
	
	socket.poll()
	var state = socket.get_ready_state()
	
	if state == WebSocketPeer.STATE_OPEN:
		# Receive commands from Python
		var got_packet = false
		while socket.get_available_packet_count() > 0:
			got_packet = true
			# print("Recieved Player Packet")
			var packet = socket.get_packet().get_string_from_utf8()
			var data = JSON.parse_string(packet)
			print(data)
			if not data:
				continue 
				
			handle_client_action.call(client, data)
		
		# Send current state back to the specific Python agent
		
		var send_client_update = got_packet or client.first_time or client.time_since_last_update >= UPDATE_INTERVAL
		if send_client_update:
			var context = get_context_packet.call(client)
			print("Sending context to client ", client.id, ": ", context)
			socket.send_text(JSON.stringify(context))
			# print("Sent Context")
			client.time_since_last_update = 0.0 # Reset the clock
			client.first_time = false
		
	elif state == WebSocketPeer.STATE_CLOSED:
		print("Client disconnected. Removing player.")
		remove_client.call(client)

		clients.erase(client.id)
		total_bots -= 1

func _ready():
	if server.listen(port) == OK:
		print("Server listening for agents on port ", port)

func _process(_delta):
	# 1. Accept new connections
	if server.is_connection_available():
		#var bot_index = total_bots;
		total_bots += 1
		var conn = server.take_connection()
		var socket = WebSocketPeer.new()
		socket.accept_stream(conn)
		
		# Create a unique ID for this client
		var client_id = socket.get_instance_id() 

		var client: AgentClient = AgentClient.new(client_id, socket, total_bots)
		clients[client_id] = client

		add_client.call(client)
		print("Spawned player for Client: ", client_id)

		
	
	# 2. Update all connected clients
	for id in clients.keys():
		update_client(clients[id], _delta)
