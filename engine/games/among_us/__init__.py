"""games.among_us — Among Us game implementation.

Extends :mod:`games.base` with kill, voting, ejection, and
imposter/crewmate role mechanics.
"""

from .game import AmongUsGame
from .actions import KillAction, ReportBodyAction
from .phases import PlayPhase, VotingPhase
