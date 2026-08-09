"""games.among_us.actions — Kill and Report actions for Among Us."""

from experiment import Param
from games.base import TargetedAction


class KillAction(TargetedAction):
    """Eliminate a target agent within range.

    Creates a dead body at the victim's position.  Witnesses within
    ``witness_distance`` are notified via their event channel.  The kill
    does NOT trigger voting — a separate :class:`ReportBodyAction` must
    be used by any agent who discovers the body.
    """

    action_key = "attack"
    params = {
        **TargetedAction.params,
        "witness_distance": Param(int, 5, "Max tiles for other agents to witness the kill"),
    }

    def __init__(self, range=3, prompt="", witness_distance=5,
                 available_to=None, conditions=None, **kwargs):
        super().__init__(range=range, prompt=prompt,
                         available_to=available_to, conditions=conditions, **kwargs)
        self.witness_distance = witness_distance

    def execute(self, actor, target_name: str, engine) -> dict | None:
        target = next((p for p in engine._get_active_players()
                       if p.name == target_name and p.agent_id != actor.agent_id), None)
        if not target:
            return None

        # Kill the target
        target.is_active = False
        engine._game_kills += 1
        engine._player_kills[actor.agent_id] = \
            engine._player_kills.get(actor.agent_id, 0) + 1

        # Create a dead body at the victim's tile
        body = {"name": target.name, "tile": target.tile}
        engine.dead_bodies.append(body)

        # Witnesses
        witnesses = [p.name for p in engine._get_active_players()
                     if p.agent_id not in (target.agent_id, actor.agent_id)
                     and engine.map.distance(target.tile, p.tile) <= self.witness_distance]

        # Push to event channels
        for p in engine._get_active_players():
            if p.agent_id == actor.agent_id:
                p.ctx.add("events", f"You killed {target.name}!")
            elif p.name in witnesses:
                p.ctx.add("events",
                          f"YOU WITNESSED: {actor.name} killed {target.name}!")
            # Non-witnesses won't know until they see the body

        engine.recent_events.append({
            "type": "kill", "victim": target.name, "killer": actor.name,
            "witnesses": witnesses})

        return {"type": "kill", "target": target.name,
                "victim": target.name, "killer": actor.name,
                "witnesses": witnesses}

    def description(self) -> str:
        return f"KillAction(range={self.range})"


class ReportBodyAction(TargetedAction):
    """Report a dead body, triggering an emergency meeting.

    Available to all agent types.  The target is the name of the dead
    body (visible in the agent's context).  On success, emits a report
    event that the game loop uses to transition into the voting phase.
    """

    action_key = "report"
    params = {
        **TargetedAction.params,
        "range": Param(int, 5, "Max tiles to see and report a body"),
        "prompt": Param(str, "Report a dead body",
                        "Description shown to the agent"),
    }

    def __init__(self, range=5, prompt="Report a dead body",
                 available_to=None, conditions=None, **kwargs):
        super().__init__(range=range, prompt=prompt,
                         available_to=available_to, conditions=conditions, **kwargs)

    def get_targets(self, engine, actor) -> list:
        """Return bodies within range (uses dead_bodies list on engine)."""
        targets = []
        for body in engine.dead_bodies:
            d = engine.map.distance(actor.tile, body["tile"])
            if d <= self.range:
                # Wrap in a lightweight object with .name for build_schema
                targets.append(type("_Body", (), {"name": body["name"],
                                                   "tile": body["tile"]})())
        return targets

    def execute(self, actor, target_name: str, engine) -> dict | None:
        # Find the body by name
        body = next((b for b in engine.dead_bodies
                     if b["name"] == target_name), None)
        if not body:
            return None

        # Remove the body (it's been reported)
        engine.dead_bodies.remove(body)

        # Notify all players
        for p in engine._get_active_players():
            p.ctx.add("events",
                      f"{actor.name} reported {body['name']}'s body!")

        engine.recent_events.append({
            "type": "report", "reporter": actor.name,
            "victim": body["name"]})

        return {"type": "report", "reporter": actor.name,
                "victim": body["name"]}

    def description(self) -> str:
        return f"ReportBodyAction(range={self.range})"
