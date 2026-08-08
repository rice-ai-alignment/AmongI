"""Condition components — composable boolean predicates.

Conditions evaluate against a ConditionContext that provides access to
engine state, agent state, and shared component instances. They are
ExperimentComponent subclasses, so they use the standard type/class
system and can be nested in JSON configs.
"""

from abc import abstractmethod

from experiment import ExperimentComponent, Param


class Condition(ExperimentComponent):
    """Abstract condition — evaluates to True or False given a context."""
    component_type = "Condition"

    @abstractmethod
    def evaluate(self, context) -> bool:
        """Evaluate this condition against the given context."""
        ...


# ── Combinators ────────────────────────────────────────────────────────────


class And(Condition):
    """True when all sub-conditions are true."""
    params = {
        "conditions": Param(list, [], "Sub-conditions — all must be true"),
    }
    def evaluate(self, context) -> bool:
        if not self.conditions:
            return True
        return all(c.evaluate(context) for c in self.conditions)
    def description(self) -> str:
        return f"and ({len(self.conditions or [])} conditions)"


class Or(Condition):
    """True when at least one sub-condition is true."""
    params = {
        "conditions": Param(list, [], "Sub-conditions — at least one must be true"),
    }
    def evaluate(self, context) -> bool:
        if not self.conditions:
            return False
        return any(c.evaluate(context) for c in self.conditions)
    def description(self) -> str:
        return f"or ({len(self.conditions or [])} conditions)"


class Not(Condition):
    """Negates a single sub-condition."""
    params = {
        "condition": Param(None, None, "Condition to negate"),
    }
    def evaluate(self, context) -> bool:
        if self.condition is None:
            return True
        return not self.condition.evaluate(context)
    def description(self) -> str:
        return "not"


# ── Comparisons ────────────────────────────────────────────────────────────


class Comparison(Condition):
    """Compare two expressions using an operator.

    ``op`` is one of ``"=="``, ``"!="``, ``"<"``, ``"<="``, ``">"``, ``">="``.
    """
    params = {
        "left": Param(None, None, "Left-hand expression"),
        "op": Param(str, "==", "Comparison operator"),
        "right": Param(None, None, "Right-hand expression"),
    }
    _OPS = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<":  lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">":  lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
    }
    def evaluate(self, context) -> bool:
        from components.expressions import Expression
        lhs = self.left.evaluate(context) if isinstance(self.left, Expression) else self.left
        rhs = self.right.evaluate(context) if isinstance(self.right, Expression) else self.right
        fn = self._OPS.get(self.op)
        if fn is None:
            raise ValueError(f"Unknown operator: {self.op!r}. Known: {list(self._OPS)}")
        return fn(lhs, rhs)
    def description(self) -> str:
        return f"compare {self.op}"


class IsTruthy(Condition):
    """True when the expression value is truthy."""
    params = {
        "value": Param(None, None, "Expression to test for truthiness"),
    }
    def evaluate(self, context) -> bool:
        from components.expressions import Expression
        v = self.value.evaluate(context) if isinstance(self.value, Expression) else self.value
        return bool(v)
    def description(self) -> str:
        return "is-truthy"


# ── Domain-specific conditions ─────────────────────────────────────────────


class AgentCountCheck(Condition):
    """Check the alive count of a named agent type.

    Example: "crewmates <= 1" → AgentCountCheck(agent_type="Crewmate", op="<=", count=1)
    """
    params = {
        "agent_type": Param(str, "", "Name of the agent type to count"),
        "op": Param(str, "<=", "Comparison operator"),
        "count": Param(int, 0, "Threshold to compare against"),
    }
    _OPS = Comparison._OPS
    def evaluate(self, context) -> bool:
        alive = context.get_alive_count(self.agent_type)
        fn = self._OPS.get(self.op)
        if fn is None:
            raise ValueError(f"Unknown operator: {self.op!r}")
        return fn(alive, self.count)
    def description(self) -> str:
        return f"count {self.agent_type} {self.op} {self.count}"


class AgentTypeCheck(Condition):
    """Check whether the current agent matches a named agent type."""
    params = {
        "agent_type": Param(str, "", "Name of the agent type to match"),
    }
    def evaluate(self, context) -> bool:
        return context.get_agent_type() == self.agent_type
    def description(self) -> str:
        return f"is-agent-type {self.agent_type}"
