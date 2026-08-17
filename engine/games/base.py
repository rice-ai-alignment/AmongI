"""games.base — Generic game framework.

GamePhase, TargetedAction, and BaseGame provide the skeleton that
game-specific modules (e.g. :mod:`games.among_us`) extend.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Optional

from experiment import ExperimentComponent, Param


# ── GamePhase ──────────────────────────────────────────────────────────────


class GamePhase(ExperimentComponent):
    """A phase of gameplay with a timeout, tick interval, and available actions.

    Subclasses implement ``on_start``, ``on_tick``, ``on_end``, and
    ``check_end`` to define phase-specific behaviour.
    """

    component_type = "GamePhase"
    params = {
        "timeout": Param(float, 30.0, "Phase duration in seconds"),
        "tick_interval": Param(float, 3.0, "Seconds between agent decision ticks"),
        "actions": Param(list, [], "Actions available during this phase", element_type=ExperimentComponent),
        "position_mode": Param(None, None, "Position mode for this phase (e.g. TilePosition)"),
    }

    def __init__(self, timeout=30.0, tick_interval=3.0, actions=None,
                 position_mode=None, **kwargs):
        super().__init__(**kwargs)
        self.timeout = timeout
        self.tick_interval = tick_interval
        self.actions = actions or []
        self.position_mode = position_mode
        self._elapsed: float = 0.0

    # ── lifecycle hooks ──────────────────────────────────────────────────

    def on_start(self, engine) -> None:
        """Called when this phase becomes active."""
        self._elapsed = 0.0

    def on_tick(self, engine, player, decision: dict) -> list[dict]:
        """Process one player's decision this tick.

        Returns a list of action dicts for logging / render events.
        The default implementation dispatches to each action's execute().
        """
        results = []
        for action in self.actions:
            if not self.has_action_for(player.agent_type_name, action.action_key):
                continue
            value = decision.get(action.action_key)
            if value and value not in ("none", ""):
                result = action.execute(player, value, engine)
                if result:
                    results.extend(result if isinstance(result, list) else [result])
        return results

    def on_end(self, engine) -> None:
        """Called when this phase ends (timeout or transition)."""
        pass

    def check_end(self, engine) -> Optional[dict]:
        """Return ``{'winner': name}`` if the game should end, or None."""
        return None

    # ── helpers ──────────────────────────────────────────────────────────

    def has_action_for(self, agent_type_name: str, action_key: str) -> bool:
        """Check whether *agent_type_name* can use *action_key* in this phase."""
        for a in self.actions:
            if a.action_key == action_key:
                available = getattr(a, "available_to", None)
                if available is None:
                    return True
                if not available:  # empty list = nobody
                    return False
                return agent_type_name in available
        return False

    def advance(self, dt: float) -> bool:
        """Advance the phase timer by *dt* seconds. Returns True if timed out."""
        self._elapsed += dt
        return self._elapsed >= self.timeout

    def description(self) -> str:
        return f"{self.__class__.__name__}({len(self.actions)} actions, {self.timeout}s)"


# ── TargetedAction ────────────────────────────────────────────────────────


class TargetedAction(ExperimentComponent):
    """An action that targets another agent within a range.

    The agent is prompted with a list of valid target names (within *range*
    tiles). Subclasses implement ``execute`` to define what happens when
    the action is performed on a target.

    Params:
        range: max tiles to reach a target
        prompt: description shown to the agent in the action schema
        available_to: list of agent type ids that can use this action
        conditions: list of Condition objects that must be satisfied
    """

    component_type = "AgentAction"
    action_key: str = "target"

    params = {
        "range": Param(int, 3, "Max tiles to reach a target"),
        "prompt": Param(str, "", "Description shown to the agent"),
        "available_to": Param(list, [], "Agent type ids that can use this action", element_type=str),
        "conditions": Param(list, [], "Conditions that must be satisfied", element_type=ExperimentComponent),
    }

    def __init__(self, range=3, prompt="", available_to=None, conditions=None, **kwargs):
        super().__init__(**kwargs)
        self.range = range
        self.prompt = prompt
        self.available_to = available_to or []
        self.conditions = conditions or []

    def get_targets(self, engine, actor) -> list:
        """Return all valid targets within range of *actor*."""
        targets = []
        for other in engine._get_active_players():
            if other.agent_id == actor.agent_id:
                continue
            d = engine.map.distance(actor.tile, other.tile)
            if d <= self.range:
                targets.append(other)
        return targets

    def build_schema(self, engine, actor) -> Optional[dict]:
        """Return a JSON Schema fragment for this action, or None if no targets."""
        targets = self.get_targets(engine, actor)
        if not targets:
            return None
        names = [t.name for t in targets]
        desc = self.prompt or f"Target to {self.action_key}. Options: {', '.join(names)}"
        return {
            "type": "string",
            "enum": [""] + names,
            "description": desc,
        }

    @abstractmethod
    def execute(self, actor, target_name: str, engine) -> Optional[dict]:
        """Perform the action on the named target. Return a log dict or None."""
        ...

    def description(self) -> str:
        return f"{self.__class__.__name__}(range={self.range})"


# ── BaseGame ──────────────────────────────────────────────────────────────


class BaseGame(ExperimentComponent):
    """Top-level game definition — owns phases, win conditions, and setup logic.

    Subclasses define *setup* (agent assignment, groups) and *transition*
    (phase-change rules). The engine calls these hooks during the game loop.
    """

    component_type = "Game"
    params = {
        "phases": Param(list, [], "GamePhase list for this game", element_type=ExperimentComponent),
        "win_conditions": Param(list, [], "WinCondition rules", element_type=ExperimentComponent),
        "agents": Param(None, None, "AgentConfig for this game"),
        "trial_count": Param(int, 1, "Number of trials (individual games) to run"),
    }

    def __init__(self, phases=None, win_conditions=None, agents=None,
                 trial_count=None, **kwargs):
        super().__init__(**kwargs)
        self.phases = phases or []
        self.win_conditions = win_conditions or []
        self.agents = agents
        self.trial_count = trial_count if trial_count is not None else 1
        self._phase_index: int = 0

    @property
    def current_phase(self) -> Optional[GamePhase]:
        if 0 <= self._phase_index < len(self.phases):
            return self.phases[self._phase_index]
        return None

    def setup(self, engine) -> None:
        """Configure agents, groups, and initial state on the engine."""
        pass

    def get_initial_phase(self) -> str:
        """Return the name of the starting phase."""
        return self.phases[0].__class__.__name__ if self.phases else ""

    def transition(self, engine, from_phase: GamePhase,
                   event: dict) -> Optional[GamePhase]:
        """Given a phase and an event, return the next phase (or None to stay).

        The default cycles through phases in order.
        """
        idx = self.phases.index(from_phase) if from_phase in self.phases else -1
        if idx >= 0 and idx + 1 < len(self.phases):
            self._phase_index = idx + 1
            return self.phases[idx + 1]
        return None

    def description(self) -> str:
        return f"{self.__class__.__name__}({len(self.phases)} phases)"
