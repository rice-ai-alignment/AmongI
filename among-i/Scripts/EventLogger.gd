# EventLogger.gd — Autoload this as "EventLogger"
# Add to Project > Project Settings > Autoload
extends Node

const VERSION = "1.0"

var _session_id: String = ""
var _session_start_usec: int = 0
var _log_path: String = ""
var _file: FileAccess = null
var _event_count: int = 0
var _buffer: Array = []
var _flush_interval_sec: float = 5.0
var _flush_timer: float = 0.0

# Per-game logging
var _game_id: String = ""
var _game_count: int = 0
var _game_file: FileAccess = null
var _game_log_path: String = ""
var _game_event_count: int = 0
var _game_start_usec: int = 0

# Emitted so UI/other systems can react without polling the file
signal event_logged(event: Dictionary)

func _ready() -> void:
	_session_id = "SESSION-%s" % Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "T")
	_session_start_usec = Time.get_ticks_usec()
	_log_path = "res://logs/%s.jsonl" % _session_id
	DirAccess.make_dir_recursive_absolute("res://logs")
	_file = FileAccess.open(_log_path, FileAccess.WRITE)
	if _file == null:
		push_error("EventLogger: could not open log file at %s" % _log_path)
	log_event("system", "session_start", {
		"version": VERSION,
		"map": get_tree().current_scene.name if get_tree().current_scene else "unknown",
	})

func _process(delta: float) -> void:
	_flush_timer += delta
	if _flush_timer >= _flush_interval_sec:
		_flush_timer = 0.0
		_flush()

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_CRASH:
		log_event("system", "session_end", {"event_count": _event_count})
		_close_game_log()
		_flush(true)

# ─── Game lifecycle ─────────────────────────────────────────────────────────

func start_game() -> void:
	_close_game_log()
	_game_count += 1
	_game_id = "GAME-%03d" % _game_count
	_game_event_count = 0
	_game_start_usec = Time.get_ticks_usec()

	# Create per-game log directory and file
	var game_dir = "res://logs/%s" % _session_id
	DirAccess.make_dir_recursive_absolute(game_dir)
	_game_log_path = "%s/%s.jsonl" % [game_dir, _game_id]
	_game_file = FileAccess.open(_game_log_path, FileAccess.WRITE)
	if _game_file == null:
		push_error("EventLogger: could not open game log at %s" % _game_log_path)

	log_event("system", "game_start", {"game_id": _game_id})

func end_game(recap: Dictionary) -> void:
	log_event("system", "game_end", {
		"game_id": _game_id,
		"recap": recap,
	})
	_flush(true)
	_close_game_log()

func _close_game_log() -> void:
	if _game_file != null:
		_game_file.flush()
		_game_file.close()
		_game_file = null
	_game_id = ""
	_game_log_path = ""

# ─── Core logging ────────────────────────────────────────────────────────────

func log_event(
	category: String,
	type: String,
	data: Dictionary = {}
) -> Dictionary:
	var elapsed_ms = (Time.get_ticks_usec() - _session_start_usec) / 1000.0
	var event := {
		"id": "%06d" % _event_count,
		"session": _session_id,
		"timestamp": Time.get_unix_time_from_system(),
		"elapsed_ms": elapsed_ms,
		"category": category,
		"type": type
	}
	if _game_id != "":
		event["game_id"] = _game_id
		event["game_event_id"] = _game_event_count
		_game_event_count += 1
	event.merge(data)
	_event_count += 1

	# Session log
	_buffer.append(event)
	event_logged.emit(event)
	if _buffer.size() >= 20:
		_flush()

	# Game log (immediate write to keep per-game file consistent)
	if _game_file != null:
		_game_file.store_line(JSON.stringify(event))

	return event

# ─── Internal ─────────────────────────────────────────────────────────────────

func _flush(force: bool = false) -> void:
	if _file == null or _buffer.is_empty(): return
	for ev in _buffer:
		_file.store_line(JSON.stringify(ev))
	_buffer.clear()
	if force:
		_file.flush()

func get_log_path() -> String:
	return _log_path

func get_session_id() -> String:
	return _session_id

func get_game_id() -> String:
	return _game_id
