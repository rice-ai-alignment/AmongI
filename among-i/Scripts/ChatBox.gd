# ChatBox.gd
# This script manages the chat log panel visible on screen.
# It's attached to a CanvasLayer (a special Godot node that always
# renders on top of the game world, like a HUD).
extends CanvasLayer

const MAX_MESSAGES = 50  # Keep only the last 50 messages to avoid memory buildup

@onready var message_container = $Panel/VBoxContainer/ScrollContainer/MessageContainer
@onready var scroll_container = $Panel/VBoxContainer/ScrollContainer

var log_file: FileAccess

func _ready():
	var datetime = Time.get_datetime_string_from_system().replace(":", "-").replace("T", "_")
	var filename = "chat_log_" + datetime + ".txt"
	var project_dir = ProjectSettings.globalize_path("res://")
	var log_dir = project_dir + "chat_logs/"
	DirAccess.make_dir_recursive_absolute(log_dir)
	var log_path = log_dir + filename
	log_file = FileAccess.open(log_path, FileAccess.WRITE)
	print("Chat log: ", log_path)

# Called by Server.gd whenever an agent sends a chat message.
# bbcode_msg: colored/bold BBCode string for the UI
# plain_msg: plain text "AgentName: message" for the log file
func add_message(bbcode_msg: String, plain_msg: String):
	var timestamp = Time.get_time_string_from_system()

	# Remove oldest message if we're at the limit
	if message_container.get_child_count() >= MAX_MESSAGES:
		message_container.get_child(0).queue_free()

	# Create a RichTextLabel so we can render BBCode (bold names, colors)
	var label = RichTextLabel.new()
	label.bbcode_enabled = true
	label.fit_content = true
	label.scroll_active = false
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("normal_font_size", 11)
	label.append_text("[" + timestamp + "] " + bbcode_msg)
	message_container.add_child(label)

	# Write plain-text entry to the log file
	if log_file:
		log_file.store_line("[" + timestamp + "] " + plain_msg)
		log_file.flush()

	# Wait one frame for the layout to update, then scroll to the bottom
	await get_tree().process_frame
	scroll_container.scroll_vertical = scroll_container.get_v_scroll_bar().max_value
