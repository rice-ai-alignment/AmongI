"""Expression components — typed values that conditions can reference.

Expressions resolve to a concrete value at evaluation time via a
ConditionContext that provides engine state, agent state, and shared
component instances.
"""

from abc import abstractmethod

from experiment import ExperimentComponent, Param


class Expression(ExperimentComponent):
    """Abstract expression — resolves to a value given a context."""
    component_type = "Value"

    @abstractmethod
    def evaluate(self, context) -> object:
        """Resolve this expression to a concrete value."""
        ...


class Literal(Expression):
    """A constant value embedded directly in the config."""
    params = {
        "value": Param(object, None, "The constant value"),
    }
    def evaluate(self, context) -> object:
        return self.value
    def description(self) -> str:
        return f"literal {self.value!r}"


class VariableRef(Expression):
    """Reference an exposed variable by dotted path.

    Paths like ``"engine._game_kills"`` or ``"self.tile.x"`` are resolved
    by the ConditionContext's ``resolve()`` method.
    """
    params = {
        "path": Param(str, "", "Dotted path to an exposed variable"),
    }
    def evaluate(self, context) -> object:
        return context.resolve(self.path)
    def description(self) -> str:
        return f"var {self.path}"


class FunctionCall(Expression):
    """Call an exposed function with expression arguments.

    ``function`` is a dotted path to a callable (e.g. ``"map.distance"``).
    ``args`` are sub-expressions evaluated before the call.
    """
    params = {
        "function": Param(str, "", "Dotted path to an exposed function"),
        "args": Param(list, [], "Argument expressions"),
    }
    def evaluate(self, context) -> object:
        resolved_args = [
            a.evaluate(context) if isinstance(a, Expression) else a
            for a in (self.args or [])
        ]
        return context.call(self.function, resolved_args)
    def description(self) -> str:
        return f"call {self.function}"
