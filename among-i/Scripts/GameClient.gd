extends RefCounted
class_name GameClient

var id: int
var socket: WebSocketPeer # Or PacketPeerUDP / WebSocketPeer
var node: Node       # Replace with your actual Player script type
var name: String = "undefined"
var color_index: int
var first_time: bool = true
var chat_context: Array = []
var tile: Vector2i
var time_since_last_update: float = 0.1 # UPDATE_INTERVAL
var position: Vector2
var is_imposter: bool = false
var is_active: bool = false
var wipe_next_update: bool = false

# A constructor to make creating them easy
func _init(_id: int, _socket, _node, _color: int):
	id = _id
	socket = _socket
	node = _node
	color_index = _color
	is_active = false
