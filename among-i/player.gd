# Player.gd
extends CharacterBody2D

var speed = 200

func move_agent(direction: String):
	velocity = Vector2.ZERO
	if direction == "left": velocity.x = -speed
	elif direction == "right": velocity.x = speed
	elif direction == "up": velocity.y = -speed
	elif direction == "down": velocity.y = speed
	
	move_and_slide()
