"""experiment.py — Base class + builder for tree-structured experiment configs.

Every swappable piece inherits from ExperimentComponent. Subclasses declare
their params schema as class-level Param descriptors, enabling automatic
validation and self-documenting experiments.

Components live in components.py. This file provides the base class,
builder, and CLI tools for loading/validating configs.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


class Param:
    """A typed parameter descriptor with default and description."""
    def __init__(self, ptype, default: Any = None, desc: str = ""):
        self.ptype = ptype
        self.default = default
        self.desc = desc


class ExperimentComponent(ABC):
    """Base for every swappable piece. Subclasses declare parameters via
    the `params` class-level dict of name → Param."""

    params: dict[str, Param] = {}

    def __init__(self, **kwargs):
        for name, param in self.params.items():
            setattr(self, name, kwargs.get(name, param.default))
        self._validate()

    def _validate(self):
        for name, param in self.params.items():
            val = getattr(self, name, None)
            if val is not None and param.ptype is not None:
                if isinstance(val, param.ptype):
                    continue
                # Allow int for float params (JSON numbers are always int or float)
                if param.ptype is float and isinstance(val, int):
                    continue
                raise TypeError(
                    f"{self.__class__.__name__}.{name}: expected {param.ptype.__name__}, "
                    f"got {type(val).__name__} ({val!r})")

    @classmethod
    def schema(cls) -> dict:
        return {name: {"type": p.ptype.__name__, "default": p.default, "desc": p.desc}
                for name, p in cls.params.items()}

    @abstractmethod
    def description(self) -> str: ...

    def to_json(self) -> dict:
        """Export this component and all nested components as a JSON-serialisable dict.
        Outputs both ``type`` (category) and ``class`` (concrete) for unambiguous
        reconstruction."""
        result = {
            "type": getattr(self, "component_type", self.__class__.__name__),
            "class": self.__class__.__name__,
        }
        for name in self.params:
            val = getattr(self, name, None)
            if isinstance(val, ExperimentComponent):
                result[name] = val.to_json()
            elif isinstance(val, list):
                result[name] = [
                    item.to_json() if isinstance(item, ExperimentComponent) else item
                    for item in val
                ]
            else:
                result[name] = val
        return result


# ── Condition context (runtime evaluation) ─────────────────────────────────


class ConditionContext:
    """Wraps engine state for condition evaluation.

    Provides ``resolve(path)`` and ``call(func, args)`` methods that
    conditions and expressions use to access exposed variables and
    functions at runtime.

    The ``scope`` dict maps root names to objects::

        {"engine": GameEngine, "map": BaseMap, "position": TilePosition, ...}

    Per-evaluation params (``self``, ``target``, etc.) can be passed to
    ``evaluate()`` and are bound into the scope for that call only.
    """

    def __init__(self, scope: dict = None):
        self._base_scope = scope or {}

    def bind(self, params: dict = None) -> "ConditionContext":
        """Return a new context with additional per-evaluation bindings.

        Use this to bind ``self`` and ``target`` for a single condition
        evaluation without mutating the shared base scope.

        Example: ``ctx.bind({"self": agent, "target": enemy})``
        """
        merged = {**self._base_scope, **(params or {})}
        return ConditionContext(merged)

    def resolve(self, path: str) -> object:
        """Resolve a dotted path to a value from the scope.

        The first segment is a scope key. Subsequent segments are
        attribute lookups on the resolved object.
        """
        parts = path.split(".")
        root_key = parts[0]
        if root_key not in self._base_scope:
            raise KeyError(
                f"VariableRef({path!r}): unknown root {root_key!r}. "
                f"Available: {list(self._base_scope)}")
        obj = self._base_scope[root_key]
        for attr in parts[1:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                return None
            # Support auto-call for zero-arg methods
            if callable(obj) and not isinstance(obj, type):
                try:
                    obj = obj()
                except TypeError:
                    pass  # method needs args — return the callable itself
        return obj

    def call(self, func_path: str, args: list) -> object:
        """Call an exposed function with the given arguments.

        ``func_path`` is a dotted path like ``"position.distance_between"``.
        The first segment is a scope key; the remainder resolves to a
        method on that object.
        """
        parts = func_path.split(".")
        root_key = parts[0]
        obj = self._base_scope.get(root_key)
        if obj is None:
            raise KeyError(f"Unknown root: {root_key!r}. Known: {list(self._base_scope)}")
        for attr in parts[1:]:
            obj = getattr(obj, attr)
        # Resolve any Expression args before calling
        from components.expressions import Expression
        resolved = []
        for a in (args or []):
            if isinstance(a, Expression):
                resolved.append(a.evaluate(self))
            else:
                resolved.append(a)
        return obj(*resolved)

    def get_alive_count(self, agent_type: str) -> int:
        """Count alive players of the given agent type name."""
        engine = self._base_scope.get("engine")
        if engine is None:
            return 0
        if hasattr(engine, "alive_count"):
            return engine.alive_count(agent_type)
        # Fallback for mock engines
        active = engine._get_active_players()
        return sum(1 for p in active if getattr(p, "agent_type_name", None) == agent_type)

    def get_agent_type(self) -> str | None:
        """Return the current agent's type name."""
        agent = self._base_scope.get("self")
        if agent is None:
            return None
        return getattr(agent, "agent_type_name", None)


# ── Builder ──────────────────────────────────────────────────────────────

class ExperimentBuilder:
    """Builds an Experiment tree from JSON, resolving Ref proxies."""

    # Populated after components.py is loaded
    COMPONENTS = {}

    @classmethod
    def register(cls, registry: dict):
        cls.COMPONENTS = registry

    @classmethod
    def build(cls, config: dict):
        from components import Experiment
        registry = {}
        root = cls._build_node(config, registry)
        cls._resolve_refs(root, registry)
        return root

    @classmethod
    def _resolve_refs(cls, node, registry: dict):
        from components.refs import Ref
        if isinstance(node, Ref) and node.ref and node.ref in registry:
            return registry[node.ref]
        if isinstance(node, ExperimentComponent):
            for key in list(node.params.keys()):
                current = getattr(node, key, None)
                if isinstance(current, Ref) and current.ref in registry:
                    setattr(node, key, registry[current.ref])
                elif isinstance(current, ExperimentComponent):
                    cls._resolve_refs(current, registry)
                elif isinstance(current, list):
                    for i, item in enumerate(current):
                        if isinstance(item, Ref) and item.ref in registry:
                            current[i] = registry[item.ref]
                        elif isinstance(item, ExperimentComponent):
                            cls._resolve_refs(item, registry)
        return node

    @classmethod
    def _build_node(cls, data: Any, registry: dict = None) -> Any:
        if registry is None:
            registry = {}
        if isinstance(data, dict) and "type" in data:
            type_name = data["type"]
            class_name = data.get("class", type_name)

            # Look up in hierarchical registry: {Type: {Class: ComponentClass}}
            type_group = cls.COMPONENTS.get(type_name)
            if type_group is None:
                raise ValueError(
                    f"Unknown component type: {type_name!r}. "
                    f"Known types: {list(cls.COMPONENTS.keys())}")
            if not isinstance(type_group, dict):
                # Backward compat: flat registry (old format)
                comp_cls = type_group
            else:
                comp_cls = type_group.get(class_name)
                if comp_cls is None:
                    raise ValueError(
                        f"Unknown component class: {class_name!r} "
                        f"for type {type_name!r}. "
                        f"Known classes: {list(type_group.keys())}")

            kwargs = {}
            for key, val in data.items():
                if key in ("type", "class"):
                    continue
                kwargs[key] = cls._build_node(val, registry)

            instance = comp_cls(**kwargs)
            cid = data.get("id", "")
            if cid:
                registry[cid] = instance
            return instance

        if isinstance(data, list):
            return [cls._build_node(item, registry) for item in data]

        return data


# ── Public API ───────────────────────────────────────────────────────────

def validate_config(path: str) -> list[str]:
    """Validate a JSON config file. Returns list of errors (empty = valid)."""
    try:
        build_experiment(path)
        return []
    except Exception as e:
        return [str(e)]


def schema_to_json(registry: dict = None) -> dict:
    """Export the full component schema as a JSON-serialisable dict.
    The dashboard can fetch this to render a config builder UI.
    Returns {Type: {description, classes: {Class: {description, params}}}}."""
    if registry is None:
        _ensure_registry()
        registry = ExperimentBuilder.COMPONENTS
    result = {}
    for type_name, classes in registry.items():
        if not isinstance(classes, dict):
            continue
        class_schemas = {}
        for class_name, cls in classes.items():
            if cls is None:
                continue
            params = {}
            for pname, param in cls.params.items():
                tn = param.ptype.__name__ if param.ptype else "component"
                params[pname] = {
                    "type": tn,
                    "default": repr(param.default) if param.default is not None else None,
                    "description": param.desc,
                }
            # Include exposes metadata if the class declares it
            exposes = getattr(cls, "exposes", None)
            class_entry = {
                "description": (cls.__doc__ or "").strip() or class_name,
                "params": params,
            }
            if exposes:
                class_entry["exposes"] = exposes
            class_schemas[class_name] = class_entry
        result[type_name] = {
            "description": f"{type_name} components",
            "classes": class_schemas,
        }
    return result


def dump_schema(registry: dict = None):
    """Print the full schema as human-readable text."""
    schema = schema_to_json(registry)
    for type_name, info in schema.items():
        print(f"\n[{type_name}]")
        for class_name, cls_info in info["classes"].items():
            print(f"  {class_name}")
            for pname, p in cls_info["params"].items():
                print(f"    {pname}: {p['type']} = {p['default']}  — {p['description']}")


def export_schema(path: str):
    """Write the component schema to a JSON file (for the dashboard)."""
    import json as _json
    schema = schema_to_json()
    with open(path, "w") as f:
        _json.dump(schema, f, indent=2)
    print(f"[Schema] Exported {len(schema)} components to {path}")


# Wire up the component registry on import
def _init_registry():
    from components import COMPONENT_REGISTRY
    ExperimentBuilder.register(COMPONENT_REGISTRY)


# Defer registration until first use
_initialized = False


def _ensure_registry():
    global _initialized
    if not _initialized:
        _init_registry()
        _initialized = True


# Patch build_experiment to init registry first
_orig_build = None


def build_experiment_from_dict(data: dict):
    """Build an Experiment tree from a config dict (JSON already parsed)."""
    _ensure_registry()
    return ExperimentBuilder.build(data)


def build_experiment(config_path: str):
    """Build an Experiment tree from a JSON config file path."""
    _ensure_registry()
    with open(config_path, "r") as f:
        data = json.load(f)
    return ExperimentBuilder.build(data)
