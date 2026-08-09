"""Win condition component — pluggable end-game rules.

A WinCondition has a ``winner`` (which agent group wins) and an optional
``condition`` (a general Condition that triggers it).  When the condition
evaluates to True, the game ends with the declared winner.

Multiple WinConditions can be listed — the first one whose condition
fires determines the outcome.
"""

from experiment import ExperimentComponent, Param
from experiment import ConditionContext


class WinCondition(ExperimentComponent):
    """Declares a winner and the condition that triggers that outcome.

    ``winner`` is the name of the agent group that wins (e.g. ``"Crewmate"``,
    ``"Imposter"``).

    ``condition`` is an optional Condition.  If *None*, this win condition
    never fires on its own (useful when the game ends only by timer).
    """
    component_type = "WinCondition"
    params = {
        "winner": Param(str, "", "Agent group that wins — must match an AgentType.id"),
        "condition": Param(None, None, "Condition that triggers this outcome (or null for timer-only)"),
    }

    def check(self, engine) -> dict | None:
        """Evaluate the condition against engine state.

        Returns ``{"winner": self.winner}`` if the condition is truthy,
        or *None* if the condition is absent / evaluates to False.
        """
        if self.condition is None:
            return None
        scope = {"engine": engine}
        # Register agent groups so VariableRef("Imposter.alive_count") works
        for name, group in getattr(engine, "_groups", {}).items():
            scope[name] = group
        ctx = ConditionContext(scope)
        if self.condition.evaluate(ctx):
            return {"winner": self.winner}
        return None

    def description(self) -> str:
        if self.condition is None:
            return f"win:{self.winner or '?'} (no trigger)"
        return f"win:{self.winner or '?'} if {self.condition.description()}"
