"""Agent action components — each action type is its own class with params."""

from experiment import ExperimentComponent, Param


class AgentAction(ExperimentComponent):
    """Base class for an agent action. Subclasses define specific behaviours.
    Each subclass sets ``action_key`` — the short name used in references
    (available_to, conditions, etc.). No separate ``name`` param needed."""

    component_type = "AgentAction"
    action_key: str = ""  # override in subclasses

    params = {
        "available_to": Param(list, [], "Agent type IDs allowed to use this action (empty = all)"),
        "conditions": Param(list, [], "Conditions that must be true for this action to be available"),
    }

    def can_execute(self, agent_state: dict) -> bool:
        """Check if this action is available given the agent's current state."""
        return True

    def execute(self, agent, decision_value, engine) -> list[dict]:
        """Perform the action. Returns a list of action-dicts for logging."""
        return []

    def schema_fragment(self) -> dict:
        """Return the JSON Schema fragment for this action's LLM output fields.
        Override in subclasses to declare what fields the LLM should output."""
        return {}

    @property
    def name(self) -> str:
        """Backward-compat: use action_key as the name identifier."""
        return self.action_key or self.__class__.__name__

    def description(self) -> str:
        return self.action_key or self.__class__.__name__


class MoveAction(AgentAction):
    """Move the agent on the tile grid."""
    action_key = "move"
    params = {
        **AgentAction.params,
        "range": Param(int, 2, "Max tiles per move in x or y"),
    }

    def can_execute(self, agent_state: dict) -> bool:
        return agent_state.get("position_mode") == "tile"

    def execute(self, agent, decision_value, engine) -> list[dict]:
        move_x = decision_value.get("move_x", 0)
        move_y = decision_value.get("move_y", 0)
        if move_x == 0 and move_y == 0:
            return []
        old = agent.tile.copy()
        nx, ny = old.x + move_x, old.y - move_y
        if not engine.map.is_walkable(nx, ny):
            return []
        from position import Tile
        agent.tile = Tile(nx, ny)
        return [{"type": "move", "from": {"x": old.x, "y": old.y},
                 "to": {"x": nx, "y": ny}}]

    def schema_fragment(self) -> dict:
        return {
            "move_x": {"type": "integer",
                       "description": "Steps horizontally: negative=left, 0=idle, positive=right."},
            "move_y": {"type": "integer",
                       "description": "Steps vertically: negative=down, 0=idle, positive=up."},
        }

    def description(self): return f"move (range {self.range})"


class ChatAction(AgentAction):
    """Send a chat message to nearby agents."""
    action_key = "chat"

    def execute(self, agent, decision_value, engine) -> list[dict]:
        msg = str(decision_value.get("chat", "")).strip()
        if not msg:
            return []
        engine._route_chat(agent, msg)
        return [{"type": "chat", "message": msg}]

    def schema_fragment(self) -> dict:
        return {"chat": {"type": "string", "description": "Chat message."}}

    def description(self): return "chat"


class AttackAction(AgentAction):
    """Attack the nearest agent within range."""
    action_key = "attack"
    params = {
        **AgentAction.params,
        "range": Param(int, 3, "Max tiles to reach a target"),
    }

    def can_execute(self, agent_state: dict) -> bool:
        return agent_state.get("is_imposter", False)

    def execute(self, agent, decision_value, engine) -> list[dict]:
        target = engine._get_closest_target(agent)
        if not target:
            return []
        return [{"type": "attack", "target": target.name}]

    def schema_fragment(self) -> dict:
        return {"attack": {"type": "string",
                           "description": "Set to 'attack' to kill nearest bot within range."}}

    def description(self): return f"attack (range {self.range})"


class VoteAction(AgentAction):
    """Cast a vote during the voting phase."""
    action_key = "vote"

    def execute(self, agent, decision_value, engine) -> list[dict]:
        vote_target = decision_value.get("vote", "skip") or "skip"
        return [{"type": "vote", "target": vote_target}]

    def schema_fragment(self) -> dict:
        return {"vote": {"type": "string",
                         "description": "Name to vote for or 'skip'."}}

    def description(self): return "vote"
