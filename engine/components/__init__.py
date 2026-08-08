"""components — Swappable experiment building blocks.

Registry is hierarchical: {Type: {Class: ComponentClass}}
Both "type" (category) and "class" (concrete) are required to identify a component.
"""

from .maps import SquareMap, CircleMap, FileMap
from .position import TilePosition
from .agents import AgentType, AgentConfig
from .actions import MoveAction, ChatAction, AttackAction, VoteAction
from .phases import FreeRoamPhase, VotingPhase
from .win_conditions import WinCondition
from .engine import EngineConfig, Experiment
from .refs import Ref
from .expressions import Literal, VariableRef, FunctionCall
from .conditions import (
    And, Or, Not, Comparison, IsTruthy,
    AgentCountCheck, AgentTypeCheck,
)

COMPONENT_REGISTRY = {
    "Map": {
        "SquareMap": SquareMap,
        "CircleMap": CircleMap,
        "FileMap": FileMap,
    },
    "Position": {
        "TilePosition": TilePosition,
    },
    "AgentAction": {
        "MoveAction": MoveAction,
        "ChatAction": ChatAction,
        "AttackAction": AttackAction,
        "VoteAction": VoteAction,
    },
    "AgentType": {
        "AgentType": AgentType,
    },
    "AgentConfig": {
        "AgentConfig": AgentConfig,
    },
    "Phase": {
        "FreeRoamPhase": FreeRoamPhase,
        "VotingPhase": VotingPhase,
    },
    "WinCondition": {
        "WinCondition": WinCondition,
    },
    "Engine": {
        "EngineConfig": EngineConfig,
    },
    "Experiment": {
        "Experiment": Experiment,
    },
    "Ref": {
        "Ref": Ref,
    },
    "Value": {
        "Literal": Literal,
        "VariableRef": VariableRef,
        "FunctionCall": FunctionCall,
    },
    "Condition": {
        "And": And,
        "Or": Or,
        "Not": Not,
        "Comparison": Comparison,
        "IsTruthy": IsTruthy,
        "AgentCountCheck": AgentCountCheck,
        "AgentTypeCheck": AgentTypeCheck,
    },
}
