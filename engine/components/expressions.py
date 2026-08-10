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


_MATH_OPS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b if b != 0 else 0,
    "%": lambda a, b: a % b if b != 0 else 0,
}


class MathOp(Expression):
    """Binary math operation on two expressions.

    ``op`` is one of + - * / %.
    ``left`` and ``right`` are sub-expressions evaluated before the operation.
    """
    params = {
        "op": Param(str, "+", "Operator: + - * / %"),
        "left": Param(None, None, "Left-hand expression"),
        "right": Param(None, None, "Right-hand expression"),
    }
    def evaluate(self, context) -> object:
        fn = _MATH_OPS.get(self.op)
        if fn is None:
            raise ValueError(f"Unknown math operator: {self.op!r}")
        left_val = self.left.evaluate(context) if isinstance(self.left, Expression) else (self.left or 0)
        right_val = self.right.evaluate(context) if isinstance(self.right, Expression) else (self.right or 0)
        return fn(left_val, right_val)
    def description(self) -> str:
        return f"({self.left or 0} {self.op} {self.right or 0})"
