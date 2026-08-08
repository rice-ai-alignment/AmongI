"""test_experiment.py — Tests for the experiment configuration system."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from experiment import (
    ExperimentComponent, Param, ExperimentBuilder,
    build_experiment, validate_config,
)
from components.refs import Ref
from components import (
    SquareMap, CircleMap, FileMap,
    TilePosition, AgentType, AgentConfig,
    FreeRoamPhase, VotingPhase, EngineConfig, Experiment,
)
from components.actions import MoveAction, ChatAction, AttackAction, VoteAction

TESTS_PASSED = 0
TESTS_FAILED = 0


def check(condition, msg):
    global TESTS_PASSED, TESTS_FAILED
    if condition:
        TESTS_PASSED += 1
        print(f"  PASS: {msg}")
    else:
        TESTS_FAILED += 1
        print(f"  FAIL: {msg}")


# ── Component instantiation ──────────────────────────────────────────────

def test_square_map():
    print("\n[SquareMap]")
    m = SquareMap(size=20)
    check(m.size == 20, "size set correctly")
    check(m.description() == "square arena (20x20)", "description")
    check(isinstance(m, ExperimentComponent), "is ExperimentComponent")

    # Default
    m2 = SquareMap()
    check(m2.size == 16, "default size = 16")


def test_circle_map():
    print("\n[CircleMap]")
    m = CircleMap(diameter=24)
    check(m.diameter == 24, "diameter set")
    check("circle" in m.description(), "description contains circle")


def test_file_map():
    print("\n[FileMap]")
    import tempfile, json, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"width": 4, "height": 4, "walkable": [[1,1],[2,2]]}, f)
        tmp = f.name
    try:
        m = FileMap(path=tmp)
        check(m.path == tmp, "path set")
        check(m.width == 4, "width from file")
        check(m.is_walkable(1, 1), "walkable tile")
        check(not m.is_walkable(0, 0), "non-walkable tile")
    finally:
        os.unlink(tmp)
    # Default path test (will fail if map_data.json doesn't exist, skip)
    # m2 = FileMap()
    # check(m2.path == "map_data.json", "default path")


def test_tile_position():
    print("\n[TilePosition]")
    mp = SquareMap(size=8)
    tp = TilePosition(map=mp)
    check(tp.map is mp, "map stored")
    check(tp.map.size == 8, "map size accessible through position")


def test_agent_actions():
    print("\n[Actions]")
    m = MoveAction(range=2)
    check(m.name == "move", "move action name")
    check(m.range == 2, "move range")
    c = ChatAction()
    check(c.name == "chat", "chat action name")
    a = AttackAction(range=3)
    check(a.name == "attack", "attack action name")
    v = VoteAction()
    check(v.name == "vote", "vote action name")


def test_agent_type():
    print("\n[AgentType]")
    actions = [MoveAction(), ChatAction(), AttackAction(range=3), VoteAction()]
    t = AgentType(name="Imposter", prompt="Kill.", actions=actions, count=2)
    check(t.name == "Imposter", "name set")
    check(t.count == 2, "count set")
    check(t.can("attack"), "can attack")
    check(not t.can("fly"), "cannot fly")
    check("Imposter x2" in t.description(), "description format")


def test_agent_config():
    print("\n[AgentConfig]")
    crew = AgentType(name="Crew", count=3, actions=[MoveAction(), ChatAction(), VoteAction()])
    imp = AgentType(name="Imp", count=1, actions=[MoveAction(), ChatAction(), AttackAction(), VoteAction()])
    cfg = AgentConfig(types=[crew, imp])
    check(cfg.total == 4, "total = 4")
    check(len(cfg.types) == 2, "2 types")


def test_phases():
    print("\n[Phases]")
    fp = FreeRoamPhase(tick_interval=2.0, max_duration=300.0)
    check(fp.tick_interval == 2.0, "tick_interval")
    check(fp.max_duration == 300.0, "max_duration")

    vp = VotingPhase(timeout=20.0, min_time=10.0)
    check(vp.timeout == 20.0, "timeout")
    check(vp.min_time == 10.0, "min_time")


def test_engine_config():
    print("\n[EngineConfig]")
    agents = AgentConfig(types=[
        AgentType(name="Crew", count=4, actions=[MoveAction(), ChatAction(), VoteAction()]),
        AgentType(name="Imp", count=1, actions=[MoveAction(), ChatAction(), AttackAction(), VoteAction()]),
    ])
    eng = EngineConfig(agents=agents, kill_distance=4, visibility_radius=6)
    check(eng.kill_distance == 4, "kill_distance")
    check(eng.visibility_radius == 6, "visibility_radius")


def test_experiment():
    print("\n[Experiment]")
    exp = Experiment(
        engine=EngineConfig(agents=AgentConfig(types=[AgentType(count=5)])),
        free_roam=FreeRoamPhase(),
        voting=VotingPhase(),
    )
    check(exp.engine is not None, "engine set")
    check(exp.free_roam is not None, "free_roam set")
    check(exp.voting is not None, "voting set")


# ── Validation ────────────────────────────────────────────────────────────

def test_validation_rejects_bad_type():
    print("\n[Validation]")
    try:
        SquareMap(size="not_an_int")
        check(False, "should have raised TypeError")
    except TypeError as e:
        check("expected int" in str(e), f"correct error: {e}")


def test_validation_accepts_valid():
    try:
        m = SquareMap(size=10)
        check(True, "valid type accepted")
    except Exception:
        check(False, "valid type should not raise")


# ── Proxy / Ref system ────────────────────────────────────────────────────

def test_ref():
    print("\n[Ref]")
    r = Ref(ref="arena")
    check(r.ref == "arena", "ref set")
    check("ref -> arena" in r.description(), "description")


# ── Builder ───────────────────────────────────────────────────────────────

def test_builder_from_json():
    print("\n[Builder from JSON]")
    exp = build_experiment(os.path.join(os.path.dirname(__file__), "experiment.json"))
    check(isinstance(exp, Experiment), "returns Experiment")
    check(isinstance(exp.engine, EngineConfig), "engine is EngineConfig")
    check(isinstance(exp.free_roam, FreeRoamPhase), "free_roam is FreeRoamPhase")
    check(isinstance(exp.voting, VotingPhase), "voting is VotingPhase")

    # Agent structure
    check(exp.engine.agents.total == 5, "5 agents total")
    check(len(exp.engine.agents.types) == 2, "2 agent types")
    check(exp.engine.agents.types[0].name == "Crewmate", "first type is Crewmate")
    check(exp.engine.agents.types[1].name == "Imposter", "second type is Imposter")
    phases = [exp.free_roam, exp.voting]
    check(exp.engine.agents.types[1].can("attack", phases), "imposter can attack")

    # Map via proxy
    pmap = exp.free_roam.position_mode.map
    check(isinstance(pmap, SquareMap), "map resolved from Ref")
    check(pmap.size == 16, "proxy resolves to correct instance")


def test_validate_config():
    print("\n[Validate config]")
    errs = validate_config(os.path.join(os.path.dirname(__file__), "experiment.json"))
    check(len(errs) == 0, f"experiment.json is valid (errors: {errs})")


# ── Schema dump ───────────────────────────────────────────────────────────

def test_schema():
    print("\n[Schema]")
    comps = ExperimentBuilder.COMPONENTS
    check("Map" in comps, "Map type registered")
    check("SquareMap" in comps.get("Map", {}), "SquareMap class registered under Map")
    check("AgentType" in comps, "AgentType type registered")
    check("AgentType" in comps.get("AgentType", {}), "AgentType class registered under AgentType")
    check("Ref" in comps, "Ref type registered")
    check("Ref" in comps.get("Ref", {}), "Ref class registered under Ref")
    check("Phase" in comps, "Phase type registered")
    check("FreeRoamPhase" in comps.get("Phase", {}), "FreeRoamPhase class registered under Phase")
    check("WinCondition" in comps, "WinCondition type registered")
    check("WinCondition" in comps.get("WinCondition", {}), "WinCondition class registered")
    check("Condition" in comps, "Condition type registered")
    check("And" in comps.get("Condition", {}), "And condition registered")
    check("Value" in comps, "Value type registered")
    check("Literal" in comps.get("Value", {}), "Literal expression registered")


# ── Expressions ────────────────────────────────────────────────────────────

def test_expressions():
    print("\n[Expressions]")
    from components.expressions import Literal, VariableRef, FunctionCall
    from experiment import ConditionContext

    ctx = ConditionContext({"engine": type("E", (), {"_game_kills": 5, "_get_active_players": lambda: []})()})

    lit = Literal(value=3)
    check(lit.evaluate(ctx) == 3, "Literal evaluates to value")
    check(lit.description() == "literal 3", "Literal description")

    var = VariableRef(path="engine._game_kills")
    check(var.evaluate(ctx) == 5, "VariableRef resolves path")
    check("_game_kills" in var.description(), "VariableRef description")


def test_conditions():
    print("\n[Conditions]")
    from components.conditions import (
        And, Or, Not, Comparison, IsTruthy,
        AgentCountCheck, AgentTypeCheck,
    )
    from experiment import ConditionContext

    # Combinators
    check(And(conditions=[]).evaluate(None) is True, "And empty = True")
    check(Or(conditions=[]).evaluate(None) is False, "Or empty = False")
    check(Not(condition=None).evaluate(None) is True, "Not None = True")

    from components.expressions import Literal
    true_cond = Comparison(left=Literal(value=1), op="==", right=Literal(value=1))
    false_cond = Comparison(left=Literal(value=1), op="==", right=Literal(value=2))
    check(true_cond.evaluate(None) is True, "Comparison 1==1 True")
    check(false_cond.evaluate(None) is False, "Comparison 1==2 False")
    check(And(conditions=[true_cond, true_cond]).evaluate(None) is True, "And all true = True")
    check(And(conditions=[true_cond, false_cond]).evaluate(None) is False, "And mixed = False")
    check(Or(conditions=[false_cond, true_cond]).evaluate(None) is True, "Or mixed = True")
    check(Not(condition=true_cond).evaluate(None) is False, "Not True = False")

    # IsTruthy
    check(IsTruthy(value=Literal(value=1)).evaluate(None) is True, "IsTruthy 1")
    check(IsTruthy(value=Literal(value=0)).evaluate(None) is False, "IsTruthy 0")

    # AgentCountCheck
    class MockEngine:
        def _get_active_players(self):
            return [
                type("P", (), {"agent_type_name": "Crewmate"})(),
                type("P", (), {"agent_type_name": "Crewmate"})(),
                type("P", (), {"agent_type_name": "Imposter"})(),
            ]
    ctx = ConditionContext({"engine": MockEngine()})
    acc = AgentCountCheck(agent_type="Crewmate", op=">=", count=2)
    check(acc.evaluate(ctx) is True, "AgentCountCheck Crewmate >=2")
    acc2 = AgentCountCheck(agent_type="Imposter", op="<=", count=0)
    check(acc2.evaluate(ctx) is False, "AgentCountCheck Imposter <=0 False")

    # AgentTypeCheck — uses "self" key in scope for the current agent
    mock_agent = type("A", (), {"agent_type_name": "Imposter"})()
    ctx2 = ConditionContext({"self": mock_agent, "engine": MockEngine()})
    check(AgentTypeCheck(agent_type="Imposter").evaluate(ctx2) is True, "AgentTypeCheck match")
    check(AgentTypeCheck(agent_type="Crewmate").evaluate(ctx2) is False, "AgentTypeCheck no match")


def test_per_phase_actions():
    print("\n[Phase Actions]")
    exp = build_experiment(os.path.join(os.path.dirname(__file__), "experiment.json"))
    fr = exp.free_roam
    check(len(fr.actions) == 3, "FreeRoam has 3 actions")
    check(fr.actions[0].available_to == ["Crewmate", "Imposter"], "MoveAction available_to")
    check(fr.actions[0].conditions == [], "MoveAction has no conditions")

    attack = [a for a in fr.actions if a.name == "attack"][0]
    check(attack.available_to == ["Imposter"], "AttackAction only for Imposter")
    check(len(attack.conditions) == 1, "AttackAction has 1 condition")
    from components.conditions import Comparison
    cond = attack.conditions[0]
    check(isinstance(cond, Comparison), "Condition is Comparison")
    check(cond.op == "<=", "Comparison operator is <=")

    # Check that the right-hand side is Literal(3)
    from components.expressions import Literal, FunctionCall
    check(isinstance(cond.right, Literal), "RHS is Literal")
    check(cond.right.value == 3, "Distance threshold is 3")
    check(isinstance(cond.left, FunctionCall), "LHS is FunctionCall to position.distance_between")
    check(cond.left.function == "position.distance_between", "Calls position.distance_between")

    vt = exp.voting
    check(len(vt.actions) == 2, "Voting has 2 actions")
    check(vt.actions[0].name == "vote", "VoteAction present")


def test_exposes():
    print("\n[Exposes]")
    from components.maps import SquareMap
    check("variables" in SquareMap.exposes, "SquareMap exposes variables")
    check("size" in SquareMap.exposes["variables"], "SquareMap exposes size")
    check("functions" in SquareMap.exposes, "SquareMap exposes functions")
    check("is_walkable" in SquareMap.exposes["functions"], "SquareMap exposes is_walkable")

    from components.engine import EngineConfig
    check("alive_count" in EngineConfig.exposes["functions"], "EngineConfig exposes alive_count function")
    check("token_limit" in EngineConfig.exposes["variables"], "EngineConfig exposes token_limit")

    # Schema export includes exposes
    from experiment import schema_to_json
    schema = schema_to_json()
    map_schema = schema.get("Map", {}).get("classes", {}).get("SquareMap", {})
    check("exposes" in map_schema, "Schema includes exposes for SquareMap")

    # TilePosition exposes position functions
    from components.position import TilePosition
    check("functions" in TilePosition.exposes, "TilePosition exposes functions")
    check("distance_between" in TilePosition.exposes["functions"], "TilePosition exposes distance_between")


def test_composable_distance():
    """Distance is computed by calling position.distance_between(id_a, id_b)
    via a FunctionCall expression, compared with Comparison. This keeps
    distance semantics in the position mode, not in a hardcoded condition."""
    print("\n[Composable Distance]")
    from components.expressions import Literal, VariableRef, FunctionCall
    from components.conditions import Comparison
    from experiment import ConditionContext
    from position import Tile

    # Mock a position mode that tracks entities by ID
    class MockPosition:
        def __init__(self):
            self._entities = {}
        def distance_between(self, id_a, id_b):
            a = self._entities.get(id_a)
            b = self._entities.get(id_b)
            if a is None or b is None:
                return None
            return ((a.x - b.x)**2 + (a.y - b.y)**2) ** 0.5

    pos = MockPosition()
    pos._entities[1] = Tile(0, 0)
    pos._entities[2] = Tile(3, 4)  # distance 5 from (0,0)

    # Condition: position.distance_between(self.id, target.id) <= 3
    cond = Comparison(
        op="<=",
        left=FunctionCall(
            function="position.distance_between",
            args=[VariableRef(path="self.id"), VariableRef(path="target.id")],
        ),
        right=Literal(value=3),
    )

    base_ctx = ConditionContext({"position": pos})
    ctx_near = base_ctx.bind({"self": type("E", (), {"id": 1})(),
                               "target": type("E", (), {"id": 1})()})  # same tile, distance 0
    check(cond.evaluate(ctx_near) is True, "distance 0 <= 3 → True")

    ctx_far = base_ctx.bind({"self": type("E", (), {"id": 1})(),
                              "target": type("E", (), {"id": 2})()})  # distance 5
    check(cond.evaluate(ctx_far) is False, "distance 5 <= 3 → False")


# ── Run all ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_square_map()
    test_circle_map()
    test_file_map()
    test_tile_position()
    test_agent_actions()
    test_agent_type()
    test_agent_config()
    test_phases()
    test_engine_config()
    test_experiment()
    test_validation_rejects_bad_type()
    test_validation_accepts_valid()
    test_ref()
    test_builder_from_json()
    test_validate_config()
    test_schema()
    test_expressions()
    test_conditions()
    test_per_phase_actions()
    test_exposes()
    test_composable_distance()

    print(f"\n{'='*50}")
    total = TESTS_PASSED + TESTS_FAILED
    print(f"Results: {TESTS_PASSED}/{total} passed, {TESTS_FAILED} failed")
    if TESTS_FAILED:
        sys.exit(1)
