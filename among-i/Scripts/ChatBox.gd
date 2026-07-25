# ChatBox.gd
# This script manages the chat log panel visible on screen.
# It's attached to a CanvasLayer (a special Godot node that always
# renders on top of the game world, like a HUD).
extends CanvasLayer

const MAX_MESSAGES = 50

@onready var message_container = $Panel/VBoxContainer/ScrollContainer/MessageContainer
@onready var scroll_container = $Panel/VBoxContainer/ScrollContainer

func _ready():
	pass

func add_message(bbcode_msg: String) -> void:
	var timestamp = Time.get_time_string_from_system()

	if message_container.get_child_count() >= MAX_MESSAGES:
		message_container.get_child(0).queue_free()

	var label = RichTextLabel.new()
	label.bbcode_enabled = true
	label.fit_content = true
	label.scroll_active = false
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("normal_font_size", 11)
	label.append_text("[" + timestamp + "] " + bbcode_msg)
	message_container.add_child(label)

	await get_tree().process_frame
	scroll_container.scroll_vertical = scroll_container.get_v_scroll_bar().max_value
