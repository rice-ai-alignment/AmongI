"""Top-level engine and experiment config components."""

from experiment import ExperimentComponent, Param


class EngineConfig(ExperimentComponent):
    """Engine-level parameters."""
    component_type = "Engine"
    exposes = {
        "variables": {
            "kill_distance": "int — max tiles for imposter kill",
            "visibility_radius": "int — radius for agent world view",
            "witness_distance": "int — max tiles to witness a kill",
            "game_kills": "int — total kills this game",
            "game_index": "int — current game number (1-based)",
            "token_limit": "int — total token budget across all agents",
            "phase": "str — current game phase name",
        },
        "functions": {
            "alive_count": {"args": ["agent_type"], "returns": "int", "desc": "Number of alive agents of the given type"},
            "nearest_enemy": {"args": [], "returns": "agent | null", "desc": "Closest enemy agent to the current agent"},
            "distance_between": {"args": ["a", "b"], "returns": "float", "desc": "Distance between two agents"},
        },
    }
    params = {
        "agents": Param(None, None, "AgentConfig defining agent types"),
        "win_conditions": Param(list, [], "List of WinCondition rules for game end"),
        "kill_distance": Param(int, 3, "Max tiles for imposter kill"),
        "visibility_radius": Param(int, 5, "Radius for agent world view"),
        "witness_distance": Param(int, 5, "Max tiles to witness a kill"),
        "token_limit": Param(int, 100000, "Total token budget across all agents"),
    }
    def description(self):
        return self.agents.description() if self.agents else "no agents"


class Experiment(ExperimentComponent):
    """Top-level experiment — composes engine, phases, map, and agents."""
    component_type = "Experiment"
    params = {
        "engine": Param(EngineConfig, None, "Engine parameters"),
        "free_roam": Param(None, None, "Free-roam phase config"),
        "voting": Param(None, None, "Voting phase config"),
    }
    def __init__(self, engine=None, free_roam=None, voting=None, **kwargs):
        super().__init__(**kwargs)
        self.engine = engine
        self.free_roam = free_roam
        self.voting = voting
    def description(self): return "experiment"
