"""experiment_runtime.py — Convert an Experiment component tree to runtime objects.

Shared by run.py and server_handler.py to avoid duplicating the
config → GameConfig/phase/map wiring.
"""

from __future__ import annotations

from engine import GameConfig
from components.maps import SquareMap


def experiment_to_runtime(exp):
    """Convert an Experiment tree into (GameConfig, free_roam, voting,
    win_conditions, position_mode, map_data).

    The map comes from the position mode component (e.g. TilePosition.map).
    Returns a tuple of (config, free_roam_phase, voting_phase, win_conditions, position_mode, map_data).
    """
    eng = exp.engine
    config = GameConfig()
    config.player_count = eng.agents.total
    config.kill_distance = eng.kill_distance
    config.visibility_radius = eng.visibility_radius
    config.witness_distance = eng.witness_distance
    if hasattr(eng, "token_limit"):
        config.token_limit = eng.token_limit
    fr = exp.free_roam
    config.agent_tick_interval = fr.tick_interval
    config.vote_timeout = exp.voting.timeout
    config.min_vote_time = exp.voting.min_time
    free_roam_phase = exp.free_roam
    voting_phase = exp.voting
    win_conditions = eng.win_conditions or []

    # Position mode owns the map — extract from the free-roam phase config
    position_mode = exp.free_roam.position_mode
    map_data = position_mode.map if position_mode else None
    if map_data is None:
        map_data = SquareMap(16)

    return (config, free_roam_phase, voting_phase, win_conditions, position_mode, map_data)
