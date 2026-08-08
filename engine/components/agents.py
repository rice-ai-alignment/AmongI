"""Agent type components — define behaviours via swappable action classes."""

from experiment import ExperimentComponent, Param


class AgentType(ExperimentComponent):
    """One agent type — its id, display name, prompt, actions, and spawn count.

    ``id`` is the machine-readable key used in references
    (``available_to``, ``VariableRef`` paths, ``alive_count``, etc.).
    ``displayName`` is the human-readable label shown in the UI.
    """
    component_type = "AgentType"
    exposes = {
        "variables": {
            "id": "str — machine-readable identifier for this agent type",
            "displayName": "str — human-readable label",
            "count": "int — number of agents of this type",
        },
        "functions": {
            "can": {"args": ["action_name"], "returns": "bool",
                    "desc": "Check if this agent type can perform an action"},
        },
    }
    params = {
        "id": Param(str, "", "Machine-readable identifier (used in references)"),
        "displayName": Param(str, "", "Human-readable display name"),
        "prompt": Param(str, "", "System prompt for this agent type"),
        "actions": Param(None, None, "List of AgentAction instances"),
        "count": Param(int, 1, "How many agents of this type to spawn"),
    }

    def __init__(self, id=None, name=None, displayName=None, actions=None, **kwargs):
        # Accept legacy 'name' as alias for 'id'
        if id is None and name is not None:
            id = name
        if displayName is None:
            displayName = id or ""
        kwargs["id"] = id
        kwargs["displayName"] = displayName
        super().__init__(**kwargs)
        self.actions = actions if actions else []

    @property
    def name(self) -> str:
        """Backward-compat alias for id."""
        return self.id

    def can(self, action_name: str) -> bool:
        if isinstance(self.actions, list):
            return any(a.name == action_name for a in self.actions)
        if hasattr(self.actions, action_name):
            return bool(getattr(self.actions, action_name))
        return False

    def description(self):
        if isinstance(self.actions, list):
            acts = ", ".join(a.name for a in self.actions)
        elif hasattr(self.actions, 'description'):
            acts = self.actions.description()
        else:
            acts = "no actions"
        label = self.displayName or self.id
        return f"{label} x{self.count} ({acts})"


class AgentConfig(ExperimentComponent):
    """Collection of agent types for an experiment."""
    component_type = "AgentConfig"
    params = {"types": Param(list, None, "List of AgentType definitions")}
    def __init__(self, types=None, **kwargs):
        super().__init__(**kwargs)
        self.types = types or []
    @property
    def total(self) -> int:
        return sum(t.count for t in self.types)
    def description(self):
        return f"{self.total} agents across {len(self.types)} types"
