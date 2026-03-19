# Player.gd
extends CharacterBody2D

var speed = 200

@onready var speech_bubble = get_parent().get_node("SpeechBubble")

func move_agent(direction: String):
	velocity = Vector2.ZERO
	if direction == "left": velocity.x = -speed
	elif direction == "right": velocity.x = speed
	elif direction == "up": velocity.y = -speed
	elif direction == "down": velocity.y = speed
	
	move_and_slide()

func _process(_delta):
	if speech_bubble != null and speech_bubble.visible:
		# Center the bubble horizontally and keep it above the sprite
		speech_bubble.position.x = -speech_bubble.size.x / 2.0
		speech_bubble.position.y = -(speech_bubble.size.y + 45.0)
