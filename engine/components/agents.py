"""Agent type components — identity, prompt, and spawn count.

Actions are defined at the *phase* level with ``available_to`` lists,
not duplicated on AgentType. Use ``has_action(action_key)`` after
the experiment tree is built to resolve capabilities from phases.
"""

from experiment import ExperimentComponent, Param


class AgentType(ExperimentComponent):
    """One agent type — its id, display name, prompt, and spawn count.

    ``id`` is the machine-readable key used in references
    (``available_to``, ``VariableRef`` paths, ``alive_count``, etc.).
    ``displayName`` is the human-readable label shown in the UI.

    Actions are defined in phases (FreeRoamPhase.actions, VotingPhase.actions)
    with ``available_to`` lists — not duplicated here.
    """

    component_type = "AgentType"
    exposes = {
        "variables": {
            "id": "str — machine-readable identifier for this agent type",
            "displayName": "str — human-readable label",
            "count": "int — number of agents of this type",
        },
        "functions": {},
    }
    params = {
        "id": Param(str, "", "Machine-readable identifier (used in references)"),
        "displayName": Param(str, "", "Human-readable display name"),
        "prompt": Param(str, "", "System prompt for this agent type"),
        "count": Param(int, 1, "How many agents of this type to spawn"),
        "context_manager": Param(None, None, "Optional ContextManager config for this type"),
    }

    def __init__(self, id=None, name=None, displayName=None, **kwargs):
        # Accept legacy 'name' as alias for 'id'
        if id is None and name is not None:
            id = name
        if displayName is None:
            displayName = id or ""
        kwargs["id"] = id
        kwargs["displayName"] = displayName
        # Backward compat: pop actions if passed directly (tests, old code)
        legacy_actions = kwargs.pop("actions", None)
        super().__init__(**kwargs)
        if legacy_actions is not None:
            self.actions = legacy_actions

    @property
    def name(self) -> str:
        """Backward-compat alias for id."""
        return self.id

    def can(self, action_key: str, phases: list = None) -> bool:
        """Check if this agent type can perform an action.
        First checks legacy ``self.actions`` list if present (backward compat).
        Otherwise scans phases for actions available to this type."""
        # Backward compat: if actions were passed directly (tests), check them
        if hasattr(self, 'actions') and self.actions:
            return any(
                (getattr(a, 'action_key', '') or getattr(a, 'name', '')) == action_key
                for a in self.actions
            )
        return self.has_action(action_key, phases)

    def has_action(self, action_key: str, phases: list = None) -> bool:
        """Check if this agent type can perform an action, by scanning phases.
        Pass the experiment's phases (free_roam, voting) to resolve capabilities."""
        if phases:
            for phase in phases:
                if not phase or not hasattr(phase, 'actions'):
                    continue
                for action in (phase.actions or []):
                    available = getattr(action, 'available_to', []) or []
                    action_name = getattr(action, 'action_key', '') or action.name
                    if (not available or self.id in available) and action_name == action_key:
                        return True
        return False

    def description(self):
        label = self.displayName or self.id
        return f"{label} x{self.count}"


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
