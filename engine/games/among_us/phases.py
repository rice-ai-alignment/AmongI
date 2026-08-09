"""games.among_us.phases — Play and Voting phases for Among Us."""

from experiment import Param
from games.base import GamePhase


class PlayPhase(GamePhase):
    """Free-roam exploration — agents move, chat, and can kill.

    A kill triggers an emergency meeting (transition to VotingPhase).
    """

    params = {
        **GamePhase.params,
        "timeout": Param(float, 600.0, "Max game duration in seconds"),
        "tick_interval": Param(float, 3.0, "Seconds between agent decision ticks"),
    }

    def __init__(self, timeout=600.0, tick_interval=3.0, actions=None, **kwargs):
        super().__init__(timeout=timeout, tick_interval=tick_interval,
                         actions=actions, **kwargs)

    def on_tick(self, engine, player, decision: dict) -> list[dict]:
        results = []

        # ── Movement ──
        move_x = decision.get("move_x", 0) or 0
        move_y = decision.get("move_y", 0) or 0
        if move_x or move_y:
            old = player.tile
            nx = old.x + move_x
            ny = old.y - move_y  # Y-up in agent view → Y-down in engine
            if engine.map.is_walkable(nx, ny):
                player.tile = type(old)(nx, ny)
                results.append({
                    "type": "move",
                    "from": {"x": old.x, "y": old.y},
                    "to": {"x": nx, "y": ny},
                })

        # ── Actions (attack, chat, etc.) ──
        for action in self.actions:
            if not self.has_action_for(player.agent_type_name, action.action_key):
                continue
            value = decision.get(action.action_key)
            if value and value not in ("none", ""):
                result = action.execute(player, value, engine)
                if result:
                    results.extend(result if isinstance(result, list) else [result])

        # ── Chat ──
        chat_msg = decision.get("chat", "")
        chat_result = engine.chat_context.route(engine, player, chat_msg)
        if chat_result:
            results.append(chat_result)

        return results

    def check_end(self, engine) -> dict | None:
        # Check configured win conditions
        for wc in engine.win_conditions:
            result = wc.check(engine)
            if result:
                return result
        return None

    def description(self) -> str:
        return f"PlayPhase({self.timeout}s, {len(self.actions)} actions)"


class VotingPhase(GamePhase):
    """Emergency meeting — agents discuss, vote, and eject one player.

    After voting concludes, checks win conditions and transitions back to
    PlayPhase (or ends the game).
    """

    params = {
        **GamePhase.params,
        "timeout": Param(float, 30.0, "Voting duration in seconds"),
        "min_time": Param(float, 15.0, "Minimum voting time before tallying"),
    }

    def __init__(self, timeout=30.0, min_time=15.0, tick_interval=3.0,
                 actions=None, **kwargs):
        super().__init__(timeout=timeout, tick_interval=tick_interval,
                         actions=actions, **kwargs)
        self.min_time = min_time
        self.votes: dict[int, str] = {}

    def on_start(self, engine) -> None:
        super().on_start(engine)
        self.votes.clear()
        engine.vote_choices.clear()

        # Build report context from the most recent event
        last_ev = engine.recent_events[-1] if engine.recent_events else {}
        report_info = ""
        if last_ev.get("type") == "report":
            report_info = (
                f"{last_ev.get('reporter', '?')} reported "
                f"{last_ev.get('victim', '?')}'s body!"
            )
        elif last_ev.get("type") == "kill":
            report_info = (
                f"{last_ev.get('victim', '?')} was found dead!"
            )

        names = [p.name for p in engine._get_active_players()]
        # Push system message
        for p in engine._get_active_players():
            msg = (f"Emergency meeting! {report_info} "
                   f"{len(names)} players voting. "
                   f"Players: {', '.join(names)}")
            p.ctx.add("events", msg)

    def on_tick(self, engine, player, decision: dict) -> list[dict]:
        results = []
        vote = decision.get("vote", "skip") or "skip"
        engine.vote_choices[player.agent_id] = vote
        self.votes[player.agent_id] = vote

        results.append({"type": "vote", "voter": player.name, "voted_for": vote})

        # Chat during voting
        chat_msg = decision.get("chat", "")
        chat_result = engine.chat_context.route(engine, player, chat_msg, broadcast=True)
        if chat_result:
            results.append(chat_result)

        return results

    def on_end(self, engine) -> None:
        """Tally votes and eject the player with the most votes."""
        tally: dict[str, int] = {}
        for target in engine.vote_choices.values():
            if target and target != "skip":
                tally[target] = tally.get(target, 0) + 1

        skips = sum(1 for v in engine.vote_choices.values() if v == "skip")
        tally_strs = [f"{name} ({c})" for name, c in tally.items()]
        if skips:
            tally_strs.append(f"skip ({skips})")

        if not tally:
            engine.recent_events.append(
                {"type": "eject", "victim": "", "role": ""})
            return

        # Plurality — pick the most-voted player
        max_votes = max(tally.values())
        winners = [name for name, c in tally.items() if c == max_votes]
        if len(winners) != 1:
            # Tie — nobody ejected
            engine.recent_events.append(
                {"type": "eject", "victim": "", "role": ""})
            return

        voted_name = winners[0]
        victim = next((p for p in engine.players.values()
                       if p.name == voted_name and p.is_active), None)
        if not victim:
            return

        victim.is_active = False
        engine._game_ejections += 1
        role_note = f" (was {victim.agent_type_name})"
        for p in engine.players.values():
            p.ctx.add("events", f"{victim.name} was ejected!{role_note}")

        engine.recent_events.append(
            {"type": "eject", "agent_id": victim.agent_id,
             "victim": victim.name, "role": victim.agent_type_name})

    def check_end(self, engine) -> dict | None:
        # Check win conditions after ejection
        for wc in engine.win_conditions:
            result = wc.check(engine)
            if result:
                return result
        return None

    def description(self) -> str:
        return f"VotingPhase({self.timeout}s, {len(self.actions)} actions)"
