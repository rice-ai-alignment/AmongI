# PlaybackController.gd — Event timeline manager for the Among-I renderer.
# Owns the event buffer, playback clock, seeking, and mode state.
# Works in two modes:
#   File replay: loads JSONL, replays with original timing, full scrubbing.
#   Live: accumulates WebSocket events for read-only progress display.

extends Node

signal time_changed(ms: float)
signal duration_changed(ms: float)
signal state_changed(playing: bool)
signal mode_changed(file_mode: bool)
signal markers_changed(markers: Array)

const SPEEDS: Array[float] = [1.0, 2.0, 4.0]

var _events: Array[Dictionary] = []
var _time_ms: float = 0.0
var _duration_ms: float = 0.0
var _dispatch_idx: int = 0
var _playing: bool = false
var _speed_index: int = 0
var _file_mode: bool = false
var _markers: Array[Dictionary] = []

var server: Node = null


func _ready():
	server = get_parent()
	server.event_received.connect(_on_server_event)


# ── Public API ──────────────────────────────────────────────────────────────

func is_file_mode() -> bool:
	return _file_mode


func is_playing() -> bool:
	return _playing


func get_time_ms() -> float:
	return _time_ms


func get_duration_ms() -> float:
	return _duration_ms


func get_speed() -> float:
	return SPEEDS[_speed_index]


func get_speed_label() -> String:
	return "%gx" % SPEEDS[_speed_index]


func get_file_name() -> String:
	if _events.is_empty():
		return ""
	# Try to guess from session id
	var first = _events[0]
	var sid = first.get("session", "")
	if sid != "":
		return sid + ".jsonl"
	return ""


# ── File loading ────────────────────────────────────────────────────────────

func load_file(path: String):
	print("[Playback] Loading: ", path)
	var file = FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("[Playback] Cannot open: " + path)
		return

	_events.clear()
	var idx := 0
	while not file.eof_at_end():
		var line = file.get_line()
		if line.strip_edges() == "":
			continue
		var json = JSON.new()
		var err = json.parse(line)
		if err == OK:
			var data = json.data
			if data is Dictionary:
				data["_sort_idx"] = idx
				_events.append(data)
				idx += 1
	file.close()

	if _events.is_empty():
		push_error("[Playback] No valid events in file")
		return
	print("[Playback] Parsed %d events" % _events.size())

	# Stable sort by elapsed_ms, tie-break by original file order.
	_events.sort_custom(func(a, b):
		var ma = a.get("elapsed_ms", 0)
		var mb = b.get("elapsed_ms", 0)
		if ma < mb: return true
		if ma > mb: return false
		return a.get("_sort_idx", 0) < b.get("_sort_idx", 0)
	)

	_duration_ms = float(_events[-1].get("elapsed_ms", 0))
	_build_markers()

	# Switch to file mode
	if not _file_mode:
		server.stop_listening()
		_file_mode = true
		mode_changed.emit(true)

	duration_changed.emit(_duration_ms)
	markers_changed.emit(_markers)

	seek(0)
	play()


# ── Playback control ────────────────────────────────────────────────────────

func play():
	_playing = true
	state_changed.emit(true)


func pause():
	_playing = false
	state_changed.emit(false)


func toggle():
	if _playing: pause()
	else: play()


func cycle_speed():
	_speed_index = (_speed_index + 1) % SPEEDS.size()


func set_speed_index(idx: int):
	_speed_index = clampi(idx, 0, SPEEDS.size() - 1)


func exit_to_live():
	pause()
	_events.clear()
	_markers.clear()
	_time_ms = 0.0
	_duration_ms = 0.0
	_dispatch_idx = 0
	_file_mode = false
	server.clear_world()
	server.start_listening()
	mode_changed.emit(false)
	duration_changed.emit(0.0)
	time_changed.emit(0.0)
	markers_changed.emit([])


# ── Seeking ─────────────────────────────────────────────────────────────────

func seek(target_ms: float):
	if _events.is_empty():
		return

	target_ms = clamp(target_ms, 0.0, _duration_ms)
	var was_playing = _playing
	_playing = false   # pause during rebuild

	var idx = _upper_bound(target_ms)
	await _rebuild(idx)

	_time_ms = target_ms
	_playing = was_playing
	time_changed.emit(target_ms)
	if _playing:
		state_changed.emit(true)


func _upper_bound(ms: float) -> int:
	var lo := 0
	var hi := _events.size()
	while lo < hi:
		var mid = (lo + hi) / 2
		if _events[mid].get("elapsed_ms", 0) <= ms:
			lo = mid + 1
		else:
			hi = mid
	return lo


func _rebuild(idx: int):
	server.clear_world()
	server.instant_mode = true
	server.silent = true

	var i := 0
	while i < idx:
		server.handle_event(_events[i])
		i += 1
		if i % 2000 == 0:
			await get_tree().process_frame

	server.instant_mode = false
	server.silent = false
	_dispatch_idx = idx


# ── Playback clock (file mode) ──────────────────────────────────────────────

func _process(delta: float):
	if not _playing or _events.is_empty():
		return

	_time_ms += delta * 1000.0 * SPEEDS[_speed_index]
	_dispatch_until(_time_ms)

	if _time_ms >= _duration_ms:
		_time_ms = _duration_ms
		_playing = false
		state_changed.emit(false)

	time_changed.emit(_time_ms)


func _dispatch_until(ms: float):
	while _dispatch_idx < _events.size():
		var ev = _events[_dispatch_idx]
		if ev.get("elapsed_ms", 0) > ms:
			break
		server.handle_event(ev)
		_dispatch_idx += 1


# ── Live mode accumulation ──────────────────────────────────────────────────

func _on_server_event(ev: Dictionary):
	if _file_mode:
		return  # don't accumulate during file replay

	var ems = ev.get("elapsed_ms", null)
	if ems != null:
		_time_ms = float(ems)
		if _time_ms > _duration_ms:
			_duration_ms = _time_ms
			duration_changed.emit(_duration_ms)
		time_changed.emit(_time_ms)


# ── Markers ─────────────────────────────────────────────────────────────────

func _build_markers():
	_markers.clear()
	for ev in _events:
		var ems = ev.get("elapsed_ms", 0)
		var etype = ev.get("type", "")
		var kind = ""
		match etype:
			"kill", "player_died":
				kind = "kill"
			"vote_cast", "start", "result", "voting_start", "voting_result":
				kind = "vote"
			"game_start", "game_end":
				kind = "boundary"
		if kind != "":
			_markers.append({"ms": float(ems), "kind": kind})
