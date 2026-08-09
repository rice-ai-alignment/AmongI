# TimelineMarkers.gd — Draws colored event markers on top of the timeline slider.
# Rendered as vertical 2px lines: kills=red, votes=orange, game boundaries=white.

extends Control

const KIND_COLORS := {
	"kill": Color("#C51111"),
	"vote": Color("#EF7D0E"),
	"boundary": Color(1.0, 1.0, 1.0, 0.7),
}

var _markers: Array[Dictionary] = []
var _duration_ms: float = 1.0


func _ready():
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func set_markers(markers: Array[Dictionary], duration_ms: float):
	_markers = markers
	_duration_ms = max(duration_ms, 1.0)
	queue_redraw()


func _draw():
	if _markers.is_empty():
		return

	var w := size.x
	var h := size.y
	var mid_y := h / 2.0

	for m in _markers:
		var ms: float = m.get("ms", 0.0)
		var kind: String = m.get("kind", "")
		var x = ms / _duration_ms * w
		var col = KIND_COLORS.get(kind, Color.WHITE)

		if kind == "boundary":
			# Full-height line for game boundaries
			draw_line(Vector2(x, 2), Vector2(x, h - 2), col, 1.0)
		else:
			# Short tick centered vertically
			var half_h := 6.0
			draw_line(Vector2(x, mid_y - half_h), Vector2(x, mid_y + half_h), col, 2.0)
