"""components — Swappable experiment building blocks.

Registry is hierarchical: {Type: {Class: ComponentClass}}
Both "type" (category) and "class" (concrete) are required to identify a component.
"""

from .maps import SquareMap, CircleMap, FileMap
from .map_visualizer import MapVisualizer
from .position import TilePosition
from .agents import AgentType, AgentConfig
from .actions import MoveAction, ChatAction, AttackAction, VoteAction
from .phases import FreeRoamPhase, VotingPhase
from .win_conditions import WinCondition
from .engine import EngineConfig, Experiment
from .refs import Ref
from .expressions import Literal, VariableRef, FunctionCall, MathOp
from .conditions import (
    And, Or, Not, Comparison, IsTruthy,
    AgentCountCheck, AgentTypeCheck,
)
from .context_manager import ContextManager, ContextChannel, ChannelType, ChatContext
from .event_manager import EventManager

# Game framework
from games.base import GamePhase as BaseGamePhase, TargetedAction, BaseGame
from games.among_us import AmongUsGame, KillAction, ReportBodyAction, PlayPhase, VotingPhase as AmongUsVotingPhase

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
        "MathOp": MathOp,
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
    "ContextManager": {
        "ContextManager": ContextManager,
    },
    "ChatContext": {
        "ChatContext": ChatContext,
    },
    "EventManager": {
        "EventManager": EventManager,
    },
    "Game": {
        "AmongUsGame": AmongUsGame,
    },
    "GamePhase": {
        "PlayPhase": PlayPhase,
        "VotingPhase": AmongUsVotingPhase,
    },
    "TargetedAction": {
        "KillAction": KillAction,
        "ReportBodyAction": ReportBodyAction,
    },
}
