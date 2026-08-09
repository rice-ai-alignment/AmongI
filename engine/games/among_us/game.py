"""games.among_us.game — AmongUsGame definition."""

import random

from games.base import BaseGame


class AmongUsGame(BaseGame):
    """Among Us — crewmates vs imposters with kills, voting, and ejection.

    Phases:
        PlayPhase — free-roam with movement, chat, and kills.
        VotingPhase — emergency meeting triggered by a kill.
    """

    component_type = "Game"
    params = {
        **BaseGame.params,
    }

    def setup(self, engine) -> None:
        """Assign agent types to players and initialise groups."""
        active_ids = list(engine.players.keys())
        if not engine._agent_types:
            raise RuntimeError("No agent types configured for AmongUsGame")

        # Build agent groups
        engine._groups.clear()
        for at in engine._agent_types:
            engine._groups[at.id] = type(
                "AgentGroup", (), {"name": at.id, "alive_count": at.count})()

        # Assign players to types based on configured counts
        type_assignments = []
        for at in engine._agent_types:
            type_assignments.extend([at.id] * at.count)
        if len(type_assignments) < len(active_ids):
            fallback = engine._agent_types[0].id
            type_assignments.extend([fallback] * (len(active_ids) - len(type_assignments)))
        random.shuffle(type_assignments)

        for pi, pid in enumerate(active_ids):
            p = engine.players[pid]
            p.agent_type_name = type_assignments[pi]
            p.is_active = True
            p.first_time = True
            p.tile = engine.map.random_walkable_tile()

            # Context from AgentType config
            at = next((t for t in engine._agent_types
                       if t.id == p.agent_type_name), None)
            p.ctx.set_constant("system", engine.BASE_PROMPT)
            if at and at.prompt:
                p.ctx.set_constant("role", at.prompt)
            if at and at.context_manager and at.context_manager.base_prompt:
                p.ctx.set_constant("system", at.context_manager.base_prompt)
            p.agent.set_intro(engine.BASE_PROMPT)

        # Print role assignments
        by_type: dict[str, list[str]] = {}
        for p in engine.players.values():
            by_type.setdefault(p.agent_type_name, []).append(p.name)
        for tname, names in by_type.items():
            print(f"[{tname}]: {names}")

    def transition(self, engine, from_phase, event: dict) -> None:
        """Report/kill event → VotingPhase; VotingPhase end → PlayPhase or game end."""
        from .phases import PlayPhase, VotingPhase

        if isinstance(from_phase, PlayPhase):
            # Report or kill triggers emergency meeting
            if event.get("type") in ("report", "kill"):
                idx = next((i for i, ph in enumerate(self.phases)
                            if isinstance(ph, VotingPhase)), -1)
                if idx >= 0:
                    self._phase_index = idx
                    return self.phases[idx]

        if isinstance(from_phase, VotingPhase):
            # Return to play (or stay ended if game over)
            idx = next((i for i, ph in enumerate(self.phases)
                        if isinstance(ph, PlayPhase)), -1)
            if idx >= 0:
                self._phase_index = idx
                return self.phases[idx]

        return None

    def description(self) -> str:
        return f"AmongUsGame({len(self.phases)} phases)"
