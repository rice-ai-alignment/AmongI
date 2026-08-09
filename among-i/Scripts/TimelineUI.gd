# TimelineUI.gd — Playback control bar (CanvasLayer).
# Provides play/pause, speed, timeline slider with event markers,
# time display, and file load / live mode buttons.
# Wires to PlaybackController via signals + direct calls.

extends CanvasLayer

@export var controller: NodePath

var _ctrl: Node = null
var _was_playing: bool = false

@onready var play_btn: Button = $Panel/MarginContainer/HBoxContainer/PlayButton
@onready var speed_btn: Button = $Panel/MarginContainer/HBoxContainer/SpeedButton
@onready var time_label: Label = $Panel/MarginContainer/HBoxContainer/TimeLabel
@onready var slider_area: Control = $Panel/MarginContainer/HBoxContainer/SliderArea
@onready var slider: HSlider = $Panel/MarginContainer/HBoxContainer/SliderArea/TimelineSlider
@onready var markers: Control = $Panel/MarginContainer/HBoxContainer/SliderArea/Markers
@onready var load_btn: Button = $Panel/MarginContainer/HBoxContainer/LoadButton
@onready var live_btn: Button = $Panel/MarginContainer/HBoxContainer/LiveButton
@onready var file_label: Label = $Panel/MarginContainer/HBoxContainer/FileLabel
@onready var file_dialog: FileDialog = $FileDialog


func _ready():
	_ctrl = get_node(controller)

	# Connect controller signals
	_ctrl.time_changed.connect(_on_time_changed)
	_ctrl.duration_changed.connect(_on_duration_changed)
	_ctrl.state_changed.connect(_on_state_changed)
	_ctrl.mode_changed.connect(_on_mode_changed)
	_ctrl.markers_changed.connect(_on_markers_changed)

	# Wire buttons
	play_btn.pressed.connect(_on_play_pressed)
	speed_btn.pressed.connect(_on_speed_pressed)
	load_btn.pressed.connect(_on_load_pressed)
	live_btn.pressed.connect(_on_live_pressed)
	file_dialog.file_selected.connect(_on_file_selected)

	# Wire slider
	slider.value_changed.connect(_on_slider_value_changed)
	slider.drag_started.connect(_on_slider_drag_started)
	slider.drag_ended.connect(_on_slider_drag_ended)

	# Adjust ChatBox panel to not overlap our bar
	var chat_panel = get_node("../ChatBox/Panel")
	if chat_panel:
		chat_panel.offset_bottom = -72

	# Initial UI state
	_on_mode_changed(_ctrl.is_file_mode())
	play_btn.text = "▶"

	# Parse CLI file argument
	_parse_cli_file_arg()


# ── CLI arg parsing ─────────────────────────────────────────────────────────

func _parse_cli_file_arg():
	var args := OS.get_cmdline_user_args()  # args after --
	for i in range(args.size()):
		var a: String = args[i]
		if a.begins_with("--file="):
			var path = a.trim_prefix("--file=")
			_ctrl.load_file(path)
			return
		if a == "--file" and i + 1 < args.size():
			_ctrl.load_file(args[i + 1])
			return

	# Also check main args (before --)
	var main_args := OS.get_cmdline_args()
	for i in range(main_args.size()):
		var a: String = main_args[i]
		if a.begins_with("--file="):
			var path = a.trim_prefix("--file=")
			_ctrl.load_file(path)
			return
		if a == "--file" and i + 1 < main_args.size():
			_ctrl.load_file(main_args[i + 1])
			return


# ── Button handlers ─────────────────────────────────────────────────────────

func _on_play_pressed():
	_ctrl.toggle()


func _on_speed_pressed():
	_ctrl.cycle_speed()
	speed_btn.text = _ctrl.get_speed_label()


func _on_load_pressed():
	file_dialog.popup_centered()


func _on_file_selected(path: String):
	_ctrl.load_file(path)


func _on_live_pressed():
	_ctrl.exit_to_live()


# ── Slider handlers ─────────────────────────────────────────────────────────

func _on_slider_value_changed(value: float):
	_ctrl.seek(value)


func _on_slider_drag_started():
	_was_playing = _ctrl.is_playing()
	if _was_playing:
		_ctrl.pause()


func _on_slider_drag_ended(value_changed: bool):
	if _was_playing:
		_ctrl.play()


# ── Controller signal handlers ──────────────────────────────────────────────

func _on_time_changed(ms: float):
	slider.set_value_no_signal(ms)
	time_label.text = "%s / %s" % [_fmt_ms(ms), _fmt_ms(_ctrl.get_duration_ms())]


func _on_duration_changed(ms: float):
	slider.max_value = ms
	slider.step = max(100.0, ms / 500.0)


func _on_state_changed(playing: bool):
	play_btn.text = "⏸" if playing else "▶"


func _on_mode_changed(file_mode: bool):
	slider.editable = file_mode
	live_btn.visible = file_mode
	load_btn.visible = not file_mode
	file_label.text = _ctrl.get_file_name() if file_mode else ""
	markers.visible = file_mode


func _on_markers_changed(m: Array):
	if markers.has_method("set_markers"):
		markers.set_markers(m, _ctrl.get_duration_ms())


# ── Keyboard shortcuts ──────────────────────────────────────────────────────

func _unhandled_input(event: InputEvent):
	if not event.is_pressed():
		return
	if not _ctrl.is_file_mode():
		return  # shortcuts only in file replay mode

	var dur = _ctrl.get_duration_ms()
	var cur = _ctrl.get_time_ms()
	var step := 1000.0  # 1 second default
	if event is InputEventKey:
		match event.keycode:
			KEY_SPACE:
				_ctrl.toggle()
				get_viewport().set_input_as_handled()

			KEY_LEFT:
				if event.shift_pressed:
					_ctrl.seek(max(0.0, cur - 5000.0))
				else:
					_ctrl.seek(max(0.0, cur - step))
				get_viewport().set_input_as_handled()

			KEY_RIGHT:
				if event.shift_pressed:
					_ctrl.seek(min(dur, cur + 5000.0))
				else:
					_ctrl.seek(min(dur, cur + step))
				get_viewport().set_input_as_handled()

			KEY_HOME:
				_ctrl.seek(0.0)
				get_viewport().set_input_as_handled()

			KEY_END:
				_ctrl.seek(dur)
				get_viewport().set_input_as_handled()

			KEY_1:
				_ctrl.set_speed_index(0)
				speed_btn.text = _ctrl.get_speed_label()
				get_viewport().set_input_as_handled()

			KEY_2:
				_ctrl.set_speed_index(1)
				speed_btn.text = _ctrl.get_speed_label()
				get_viewport().set_input_as_handled()

			KEY_3:
				_ctrl.set_speed_index(2)
				speed_btn.text = _ctrl.get_speed_label()
				get_viewport().set_input_as_handled()


# ── Helpers ─────────────────────────────────────────────────────────────────

func _fmt_ms(ms: float) -> String:
	var total_sec := int(ms / 1000.0)
	var hours := total_sec / 3600
	var minutes := (total_sec % 3600) / 60
	var seconds := total_sec % 60
	if hours > 0:
		return "%d:%02d:%02d" % [hours, minutes, seconds]
	return "%d:%02d" % [minutes, seconds]
