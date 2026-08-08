"""Game phase components — each phase owns its behaviour, not just its config.

The engine delegates to the active phase for context building, action processing,
and end-condition checks.
"""

from abc import abstractmethod

from experiment import ExperimentComponent, Param


class GamePhase(ExperimentComponent):
    """Abstract phase — engine delegates tick logic here."""
    component_type = "Phase"
    params = {
        "actions": Param(list, [], "Actions available during this phase"),
    }

    @abstractmethod
    def build_agent_context(self, player, world_view: str, nearby: list[dict],
                            engine_state: dict) -> str:
        """Return the prompt context for one agent during this phase."""
        ...

    @abstractmethod
    def process_decision(self, player, decision: dict, engine) -> list[dict]:
        """Process an agent's decision. Returns a list of action dicts for logging."""
        ...

    @abstractmethod
    def check_end(self, engine) -> dict | None:
        """Return {'winner': 'crewmates'|'imposters'} if phase should end, else None."""
        ...


class FreeRoamPhase(GamePhase):
    """Exploration — agents move, chat, and imposters can kill."""

    params = {
        **GamePhase.params,
        "position_mode": Param(None, None, "Position system for movement"),
        "tick_interval": Param(float, 3.0, "Seconds between agent ticks"),
        "max_duration": Param(float, 600.0, "Maximum phase duration in seconds"),
    }

    def __init__(self, position_mode=None, **kwargs):
        super().__init__(**kwargs)
        self.position_mode = position_mode

    def description(self): return "free-roam exploration phase"

    def build_agent_context(self, player, world_view: str, nearby: list[dict],
                            engine_state: dict) -> str:
        """Build per-turn free-roam context for one agent."""
        ctx = player.ctx
        # Temporary per-turn info
        ctx.set_temporary("world_view", world_view)
        if player.first_time:
            ctx.set_temporary("first_turn",
                "This is your first turn — introduce yourself!")
            player.first_time = False
        else:
            ctx.channels.pop("first_turn", None)
        if nearby:
            bot_lines = "\n".join(
                f"  {b['name']}: dx={b['delta_x']:+d}, dy={b['delta_y']:+d} (dist {b['distance']:.0f})"
                for b in nearby)
            ctx.set_temporary("nearby_bots", f"Other bots visible to you:\n{bot_lines}")
        else:
            ctx.set_temporary("nearby_bots", "No other bots nearby.")
        return ctx.build_prompt()

    def process_decision(self, player, decision: dict, engine) -> list[dict]:
        """Process a single agent's free-roam decision. Returns action list."""
        actions = []
        move_x = decision.get("move_x", 0)
        move_y = decision.get("move_y", 0)
        chat_msg = str(decision.get("chat", "")).strip()
        attack = str(decision.get("attack", "")).strip().lower()

        # Move
        if move_x != 0 or move_y != 0:
            old = player.tile.copy()
            nx, ny = old.x + move_x, old.y - move_y
            if engine.map.is_walkable(nx, ny):
                from position import Tile
                player.tile = Tile(nx, ny)
                actions.append({
                    "type": "move",
                    "from": {"x": old.x, "y": old.y},
                    "to": {"x": nx, "y": ny},
                })

        # Attack
        if attack and attack not in ("none", "") and player.is_imposter:
            target = engine._get_closest_target(player)
            if target:
                actions.append({"type": "attack", "target": target.name})
                # Delegate kill handling to engine (affects global state)
                return actions  # engine will handle kill + voting transition

        # Chat
        if chat_msg:
            actions.append({"type": "chat", "message": chat_msg})
            engine._route_chat(player, chat_msg)

        return actions

    def check_end(self, engine) -> dict | None:
        """Check win condition after a kill."""
        crew = sum(1 for p in engine._get_active_players() if not p.is_imposter)
        imp = sum(1 for p in engine._get_active_players() if p.is_imposter)
        if imp == 0 and (crew + imp) > 0:
            return {"winner": "crewmates"}
        elif crew <= imp and (crew + imp) > 0:
            return {"winner": "imposters"}
        return None


class VotingPhase(GamePhase):
    """Emergency meeting — agents discuss and vote."""

    params = {
        **GamePhase.params,
        "timeout": Param(float, 30.0, "Seconds until voting ends"),
        "min_time": Param(float, 15.0, "Minimum seconds before finalising"),
    }

    def description(self): return "voting / emergency meeting phase"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.votes: dict[int, str] = {}
        self.elapsed: float = 0.0

    def reset(self):
        self.votes.clear()
        self.elapsed = 0.0

    def build_agent_context(self, player, world_view: str, nearby: list[dict],
                            engine_state: dict) -> str:
        """Build voting-phase context for one agent."""
        ctx = player.ctx
        player_names = [p.name for p in engine_state.get("active_players", [])]
        vote_info = f"VOTING PHASE — Discuss and vote.\nPlayers: {', '.join(player_names)}\n"
        vote_info += "Current votes:\n"
        for voter_id, target in self.votes.items():
            vp = engine_state.get("player_map", {}).get(voter_id)
            vote_info += f"  {vp.name if vp else '?'} -> {target}\n"
        ctx.set_temporary("voting", vote_info)
        return ctx.build_prompt()

    def process_decision(self, player, decision: dict, engine) -> list[dict]:
        """Record a vote. Returns action list."""
        vote_target = decision.get("vote", "skip") or "skip"
        self.votes[player.agent_id] = vote_target
        actions = [{"type": "vote", "target": vote_target,
                    "votes_so_far": len(self.votes)}]
        chat_msg = str(decision.get("chat", "")).strip()
        if chat_msg:
            engine._route_chat(player, chat_msg, broadcast=True)
            actions.append({"type": "chat", "message": chat_msg})
        return actions

    def tally(self) -> dict:
        """Count votes and return {ejected, was_imposter, tallies}."""
        totals: dict[str, int] = {}
        for t in self.votes.values():
            totals[t] = totals.get(t, 0) + 1
        if not totals:
            return {"ejected": "", "was_imposter": False, "tallies": totals}
        max_votes = max(totals.values())
        winners = [n for n, c in totals.items() if c == max_votes]
        if len(winners) != 1 or winners[0] == "skip":
            return {"ejected": "", "was_imposter": False, "tallies": totals}
        return {"ejected": winners[0], "was_imposter": False, "tallies": totals}

    def can_finalise(self) -> bool:
        return self.elapsed >= self.min_time

    def check_end(self, engine) -> dict | None:
        return None  # Voting doesn't end the game directly — engine handles it
