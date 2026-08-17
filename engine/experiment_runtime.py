"""experiment_runtime.py — Convert a BaseGame (AmongUsGame, etc.) to runtime objects.

Shared by run.py and server_handler.py to avoid duplicating the
config -> GameConfig/phase/map wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _RuntimeConfig:
    """Minimal config bag passed to GameEngine — mirrors engine.GameConfig
    without importing engine.py (which pulls in openai, etc.)."""
    kill_distance: int = 3
    chat_distance: int = 10000
    witness_distance: int = 5
    start_countdown: float = 5.0
    game_max_length: float = 600.0
    vote_timeout: float = 30.0
    min_vote_time: float = 15.0
    visibility_radius: int = 5
    agent_tick_interval: float = 3.0
    near_timeout_threshold: float = 5.0
    player_count: int = 5
    token_limit: int = 100000
    agent_names: list[str] = field(default_factory=lambda: [
        "Red", "Blue", "Green", "Pink", "Orange",
        "Yellow", "Black", "White", "Purple", "Brown",
    ])
    agent_colors: list[str] = field(default_factory=lambda: [
        "#C51111", "#132ED2", "#117F2D", "#ED54BB", "#EF7D0E",
        "#C8CD00", "#3F474E", "#D85A30", "#378ADD", "#1D9E75",
    ])


def _get_square_map(size=16):
    """Lazy-import SquareMap."""
    from components.maps import SquareMap
    return SquareMap(size)


def experiment_to_runtime(exp):
    """Convert a BaseGame (e.g. AmongUsGame) into runtime objects.

    Returns a tuple of (config, play_phase, voting_phase,
    win_conditions, position_mode, map_data, agent_types).
    """
    from games.base import BaseGame

    if not isinstance(exp, BaseGame):
        raise TypeError(f"Expected a BaseGame, got {type(exp).__name__}")

    config = _RuntimeConfig()

    # Agent types
    agent_types = []
    if exp.agents and hasattr(exp.agents, "types"):
        agent_types = exp.agents.types
        config.player_count = sum(getattr(t, "count", 1) for t in agent_types)

    # Phases — first is play, second is voting (if present)
    play_phase = None
    voting_phase = None
    for p in (exp.phases or []):
        if play_phase is None:
            play_phase = p
        elif voting_phase is None:
            voting_phase = p

    if play_phase:
        config.agent_tick_interval = getattr(play_phase, "tick_interval", 3.0)

    if voting_phase:
        config.vote_timeout = getattr(voting_phase, "timeout", 30.0)
        config.min_vote_time = getattr(voting_phase, "min_time", 10.0)

    win_conditions = exp.win_conditions or []

    # Position mode — on the play phase, which owns the map
    position_mode = None
    if play_phase:
        position_mode = getattr(play_phase, "position_mode", None)

    # Map — from position_mode.map
    map_data = None
    if position_mode and hasattr(position_mode, "map"):
        map_data = position_mode.map
    if map_data is None:
        print("[Runtime] No map on position_mode — falling back to SquareMap(16)")
        map_data = _get_square_map(16)

    return (config, play_phase, voting_phase, win_conditions, position_mode,
            map_data, agent_types)
