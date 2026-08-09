#!/usr/bin/env python3
"""engine.py — Python game engine for Among-I.

Owns all game logic: state machine, player management, map navigation,
prompt building, LLM orchestration, decision processing, and render events.

Agents are loaded directly via agent.agent.Agent — no WebSocket needed.
Godot rendering is optional (--render).

Usage:
    python engine.py                      # headless (default 5 players)
    python engine.py --render             # with Godot on :8081
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import dotenv

# Local imports (everything is in engine/ now)
_sys_base = os.path.dirname(os.path.abspath(__file__))
if _sys_base not in sys.path:
    sys.path.insert(0, _sys_base)

from agent import Agent
from position import Tile
from components.maps import SquareMap, CircleMap, FileMap, _MapBase as BaseMap
from components.map_visualizer import MapVisualizer
from components.context_manager import ContextManager, ChatContext

from render_client import RenderClient
from event_store import EventStore


# ── Configuration ─────────────────────────────────────────────────────────

dotenv.load_dotenv()

VERBOSE = os.getenv("VERBOSE", "0").strip() == "1"


@dataclass
class GameConfig:
    kill_distance: int = 3
    chat_distance: int = 10000
    witness_distance: int = 5
    start_countdown: float = 5.0
    game_max_length: float = 600.0
    vote_timeout: float = 30.0
    min_vote_time: float = 15.0
    visibility_radius: int = 5
    agent_tick_interval: float = 3.0
    near_timeout_threshold: float = 5.0
    player_count: int = 5
    token_limit: int = 100000

    agent_names: list[str] = field(default_factory=lambda: [
        "Red", "Blue", "Green", "Pink", "Orange",
        "Yellow", "Black", "White", "Purple", "Brown",
    ])
    agent_colors: list[str] = field(default_factory=lambda: [
        "#C51111", "#132ED2", "#117F2D", "#ED54BB", "#EF7D0E",
        "#C8CD00", "#3F474E", "#D85A30", "#378ADD", "#1D9E75",
    ])


# ── Game Phase ────────────────────────────────────────────────────────────

class Phase(Enum):
    WAITING = 0
    STARTING = 1
    PLAYING = 2
    VOTING = 3


# ── Player State ──────────────────────────────────────────────────────────

@dataclass
class AgentGroup:
    """Runtime stats for one agent type group. Registered in scope so
    conditions can reference e.g. ``Imposter.alive_count``."""
    name: str
    _engine: object = None  # back-reference to GameEngine for live counting

    @property
    def alive_count(self) -> int:
        if self._engine is None:
            return 0
        return sum(1 for p in self._engine._get_active_players()
                   if getattr(p, "agent_type_name", None) == self.name)


@dataclass
class PlayerState:
    agent_id: int
    name: str
    tile: Tile
    agent: Agent
    @property
    def is_imposter(self) -> bool:
        """Backward-compat: True if this player has an attack-capable role."""
        return self.agent_type_name.lower() in ("imposter", "impostor")
    is_active: bool = False
    color_index: int = 0
    index: int = 0
    first_time: bool = True
    agent_type_name: str = ""
    ctx: ContextManager | None = None


# ── Prompt Templates ──────────────────────────────────────────────────────

BASE_PROMPT = """You are a bot. Wander around and chat with other bots. Chat word limit is 10 per message.
You can move two tiles in the x and y directions each turn including diagonals, or choose to stay idle.
You can also respond to others or say something in chat. Provide your response in a structured format with 'move', 'chat', and 'reason' fields.
You are a 2D grid explorer. Your surroundings are represented by an ASCII grid where @ is You (always the center),
 . is Walkable ground, and # is a Wall or obstacle.
"""

# Role instructions now come from AgentType.prompt in the experiment config.

VOTE_PROMPT = """VOTING PHASE: Discuss and then cast your vote.
You cannot move or attack during voting.
After 30 seconds the player with the most votes will be ejected.
"""


# ── Persona Loading ───────────────────────────────────────────────────────

def load_personas(persona_dir: str, count: int) -> list[str]:
    import glob
    files = glob.glob(os.path.join(persona_dir, "*.txt"))
    if not files:
        print("[Engine] No persona files found — using defaults")
        return ["You are a generic helpful bot."] * count
    picked = random.sample(files, min(count, len(files)))
    return [open(fp, "r", encoding="utf-8").read().strip() for fp in picked]


# ── Map Data ──────────────────────────────────────────────────────────────

# ── Game Engine ───────────────────────────────────────────────────────────

class GameEngine:

    def __init__(self, config: GameConfig, map_data: BaseMap,
                 event_store: EventStore, render_client: Optional[RenderClient],
                 personas: list[str],
                 free_roam_phase=None, voting_phase=None, win_conditions=None,
                 position_mode=None):
        self.cfg = config
        self.map = map_data
        self.position_mode = position_mode  # e.g. TilePosition — owns the map
        self.visualizer = MapVisualizer(map_data)
        self.events = event_store
        self.render = render_client
        self.personas = personas
        self.free_roam_phase = free_roam_phase
        self.voting_phase = voting_phase
        self.win_conditions = win_conditions or []
        self._agent_types: list = []  # AgentType config objects from experiment

        self.phase: Phase = Phase.WAITING
        self.players: dict[int, PlayerState] = {}
        self._groups: dict[str, AgentGroup] = {}  # name → AgentGroup
        self._game_timer: float = 0.0
        self._state_timer: float = 0.0
        self._phase_id: int = 0
        self._tick: int = 0
        self._game_index: int = 0
        self._game_kills: int = 0
        self._game_ejections: int = 0
        self._player_kills: dict[int, int] = {}

        self.vote_choices: dict[int, str] = {}
        self._last_vote_log_second: int = -1

        self.chat_context = ChatContext()
        self.recent_events: list[dict] = []
        self._clear_memory_flags: dict[int, bool] = {}

        # Trace log — writes every prompt, response, and action
        self._trace_file = None          # session-level trace
        self._game_trace_file = None     # per-game trace
        self._experiment_config: dict = {}  # set by run.py for config export
        self._recaps: list[dict] = []        # accumulated game summaries for run() return

    def _trace(self, category: str, data: dict):
        """Write a trace event to both session and per-game trace files."""
        entry = {
            "timestamp": time.time(),
            "tick": self._tick,
            "phase": self.phase.name,
            "phase_id": self._phase_id,
            "category": category,
            **data,
        }
        payload = json.dumps(entry, indent=2) + "\n\n"
        if self._trace_file:
            self._trace_file.write(payload)
            self._trace_file.flush()
        if self._game_trace_file:
            self._game_trace_file.write(payload)
            self._game_trace_file.flush()

    def _open_trace(self):
        if self.events.session_id:
            trace_dir = os.path.join(self.events.log_dir, self.events.session_id)
            os.makedirs(trace_dir, exist_ok=True)
            trace_path = os.path.join(trace_dir, "trace.jsonl")
            self._trace_file = open(trace_path, "w", encoding="utf-8")
            print(f"[Engine] Trace log: {os.path.abspath(trace_path)}")
            # Export experiment config at session level
            if self._experiment_config:
                config_path = os.path.join(trace_dir, "config.json")
                with open(config_path, "w") as cf:
                    json.dump(self._experiment_config, cf, indent=2)
                print(f"[Engine] Config exported: {os.path.abspath(config_path)}")

    def _close_trace(self):
        if self._trace_file:
            self._trace_file.close()
            self._trace_file = None
        if self._game_trace_file:
            self._game_trace_file.close()
            self._game_trace_file = None

    # ── State helpers ─────────────────────────────────────────────────

    async def _emit(self, category: str, event_type: str, data: dict) -> dict:
        """Log an event and send the SAME event dict to Godot.
        This ensures the packet sent to Godot is identical to what appears
        in the game logs."""
        event = self.events.log_event(category, event_type, data)
        if self.render:
            await self.render.send_event(event)
        return event

    def _bump_phase(self):
        self._phase_id += 1

    def _get_active_players(self) -> list[PlayerState]:
        return [p for p in self.players.values() if p.is_active]

    @property
    def game_index(self) -> int:
        return self._game_index

    @property
    def game_kills(self) -> int:
        return self._game_kills

    def alive_count(self, agent_type: str) -> int:
        """Generic count of alive players matching a given agent type name."""
        return sum(1 for p in self._get_active_players()
                   if getattr(p, "agent_type_name", None) == agent_type)

    def _token_budget_exceeded(self) -> bool:
        """Check if any agent has exceeded its token budget."""
        for p in self.players.values():
            if p.agent.tokens.total_used >= p.agent.tokens.limit:
                print(f"[Engine] Token budget exceeded by {p.name} "
                      f"({p.agent.tokens.total_used}/{p.agent.tokens.limit})")
                return True
        return False

    def check_win_condition(self) -> dict:
        """Check win conditions — delegates to configured WinConditions."""
        for wc in self.win_conditions:
            result = wc.check(self)
            if result and result.get("winner"):
                return {"game_over": True, "winner": result["winner"]}
        return {"game_over": False, "winner": ""}

    # ── Prompt building ───────────────────────────────────────────────

    def build_intro(self, player: PlayerState) -> str:
        """Static introduction — always the first system message."""
        intro = BASE_PROMPT
        intro += f"Your name is {player.name}.\n"
        if player.first_time:
            intro += "This is your first turn — introduce yourself!\n"
            player.first_time = False
        # Use agent type prompt from config if available
        at = next((t for t in self._agent_types if t.id == player.agent_type_name), None)
        if at and at.prompt:
            intro += at.prompt
        return intro

    def build_recent_context(self, player: PlayerState, world_view: str,
                             bots: list[dict]) -> str:
        """Per-turn situational context — world view and nearby bots only.
        Chat and event messages are already in the agent's persistent history."""
        parts = []
        parts.append(f"Your current local map view is:\n{world_view}")
        lines = ["Other bots visible to you:"]
        if not bots:
            lines.append("None nearby")
        else:
            for bot in bots:
                lines.append(f"  {bot.get('name', 'Unknown')}: dx={bot.get('delta_x', 0):+d}, dy={bot.get('delta_y', 0):+d} (dist {bot.get('distance', 0):.0f})")
        parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def get_action_schema(self, player: PlayerState, is_voting: bool) -> dict:
        if is_voting:
            return {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "vote": {"type": "string", "description": "Name to vote for or 'skip'"},
                    "chat": {"type": "string", "description": "Chat message to broadcast during voting"},
                }, "required": ["vote"],
            }
        props = {
            "move_x": {"type": "integer", "description": "Steps horizontally: negative=left, 0=idle, positive=right."},
            "move_y": {"type": "integer", "description": "Steps vertically: negative=down, 0=idle, positive=up."},
            "chat": {"type": "string", "description": "Chat message."},
            "reason": {"type": "string", "description": "Logic behind the move."},
        }
        # Attack: list valid target names within range so the agent can choose.
        phase = self.voting_phase if is_voting else self.free_roam_phase
        if phase and phase.has_action_for(player.agent_type_name, "attack"):
            targets = self._get_attackable_targets(player)
            if targets:
                target_names = [t.name for t in targets]
                props["attack"] = {
                    "type": "string",
                    "enum": [""] + target_names,
                    "description": f"Target to attack. Options: {', '.join(target_names)}. Leave empty to not attack.",
                }
        return {
            "type": "object", "additionalProperties": False,
            "properties": props,
            "required": ["move_x", "move_y", "chat", "reason"],
        }

    def get_relative_player_data(self, observer: PlayerState,
                                  other: PlayerState) -> dict:
        dx = other.tile.x - observer.tile.x
        dy = other.tile.y - observer.tile.y
        return {
            "distance": math.sqrt(dx*dx + dy*dy),
            "delta_x": dx, "delta_y": -dy,
            "name": other.name,
        }

    # ── Agent calling ─────────────────────────────────────────────────

    async def _ask_agents(self, players: list[PlayerState],
                           is_voting: bool = False) -> dict[int, dict]:
        """Call each agent's LLM in parallel via thread pool. Returns agent_id -> decision."""
        phase = self._phase_id
        async def _call_one(p: PlayerState) -> tuple[int, dict]:
            # Set temporary per-turn context
            if p.first_time:
                p.ctx.set_temporary("first_turn", "This is your first turn — introduce yourself!")
                p.first_time = False
            else:
                p.ctx.channels.pop("first_turn", None)

            # World view + nearby bots
            radius = self.cfg.visibility_radius
            world_view = self.visualizer.render(p.tile, radius)
            p.ctx.set_temporary("world_view", world_view)

            other_bots = []
            for other in self._get_active_players():
                if other.agent_id == p.agent_id:
                    continue
                rel = self.get_relative_player_data(p, other)
                if abs(rel["delta_x"]) <= radius and abs(rel["delta_y"]) <= radius:
                    other_bots.append(rel)
            if other_bots:
                bot_lines = "\n".join(
                    f"  {b['name']}: dx={b['delta_x']:+d}, dy={b['delta_y']:+d} (dist {b['distance']:.0f})"
                    for b in other_bots)
                p.ctx.set_temporary("nearby_bots", f"Other bots visible to you:\n{bot_lines}")
            else:
                p.ctx.set_temporary("nearby_bots", "No other bots nearby.")

            # Voting context
            if is_voting:
                player_names = [pl.name for pl in self._get_active_players()]
                vote_info = f"Players: {', '.join(player_names)}\n"
                vote_info += "Current votes:\n"
                for voter_id, target in self.vote_choices.items():
                    vp = self.players.get(voter_id)
                    vote_info += f"  {vp.name if vp else 'Unknown'} -> {target}\n"
                p.ctx.set_temporary("voting", vote_info)

            # Build context dict for the agent
            prompt = p.ctx.build_prompt()
            action_schema = self.get_action_schema(p, is_voting)
            ctx_dict = {
                "prompt": prompt,
                "action_schema": action_schema,
                "phase_id": phase,
                "agent_type": p.agent_type_name,
                "name": p.name,
            }
            decision = await asyncio.to_thread(p.agent.think, ctx_dict)
            # Trace
            api_msgs = []
            for m in p.agent.last_api_messages:
                content = m.get("content", "")
                try:
                    parsed = json.loads(content)
                    api_msgs.append({"role": m["role"], "content": parsed})
                except (json.JSONDecodeError, TypeError):
                    api_msgs.append({"role": m["role"], "content": content})
            self._trace("context", {"agent_id": p.agent_id,
                                     "agent": p.name,
                                     "messages": api_msgs})
            decision["phase_id"] = phase
            self._trace("decision", {"agent_id": p.agent_id,
                                     "agent": p.name,
                                     "decision": decision})
            return (p.agent_id, decision)

        tasks = [asyncio.create_task(_call_one(p)) for p in players]
        results = {}
        for task in asyncio.as_completed(tasks):
            try:
                aid, decision = await task
                results[aid] = decision
            except Exception:
                pass
        return results

    # ── Decision processing ───────────────────────────────────────────

    async def _process_playing_action(self, player: PlayerState,
                                      decision: dict):
        move_x = decision.get("move_x", 0)
        move_y = decision.get("move_y", 0)
        chat_msg = str(decision.get("chat", "")).strip()
        attack = str(decision.get("attack", "")).strip().lower()

        actions = []

        # ── Move ──
        if move_x != 0 or move_y != 0:
            old = player.tile.copy()
            nx, ny = old.x + move_x, old.y - move_y
            if self.map.is_walkable(nx, ny):
                player.tile = Tile(nx, ny)
                actions.append({
                    "type": "move",
                    "from": {"x": old.x, "y": old.y},
                    "to": {"x": nx, "y": ny},
                })

        # ── Attack ──
        can_attack = self.free_roam_phase and \
            self.free_roam_phase.has_action_for(player.agent_type_name, "attack")
        if attack and attack not in ("none", "") and can_attack:
            # Look up target by name from the LLM's choice
            target = next((p for p in self._get_active_players()
                          if p.name == attack and p.agent_id != player.agent_id), None)
            if target and self.map.distance(player.tile, target.tile) <= self.cfg.kill_distance:
                actions.append({"type": "attack", "target": target.name})
                await self._kill_player(target, player)

        # ── Chat ──
        chat_action = self.chat_context.route(self, player, chat_msg)
        if chat_action:
            actions.append(chat_action)

        # ── Emit combined event (log + Godot) ──
        if actions:
            await self._emit("action", "actions", {
                "agent_id": player.agent_id,
                "actor": player.name,
                "actions": actions,
            })
            self._trace("action", {"agent_id": player.agent_id,
                                    "agent": player.name,
                                    "actions": actions})

    async def _process_voting_action(self, player: PlayerState, decision: dict):
        vote_target = decision.get("vote", "skip") or "skip"
        self.vote_choices[player.agent_id] = vote_target
        active_n = len(self._get_active_players())
        print(f"VOTING: {player.name} -> {vote_target}  "
              f"({len(self.vote_choices)}/{active_n} votes)")

        actions = [{
            "type": "vote",
            "voted_for": vote_target,
            "votes_so_far": len(self.vote_choices),
            "total_players": active_n,
        }]

        chat_msg = str(decision.get("chat", "")).strip()
        chat_action = self.chat_context.route(self, player, chat_msg, broadcast=True)
        if chat_action:
            actions.append(chat_action)

        await self._emit("voting", "vote_cast", {
            "agent_id": player.agent_id,
            "voter": player.name,
            "actions": actions,
        })
        self._trace("action", {"agent_id": player.agent_id,
                                "agent": player.name,
                                "actions": actions})

    # ── Kill logic ────────────────────────────────────────────────────

    def _get_attackable_targets(self, attacker: PlayerState) -> list[PlayerState]:
        """Return all active players within kill_distance (excluding self)."""
        targets = []
        for other in self._get_active_players():
            if other.agent_id == attacker.agent_id:
                continue
            d = self.map.distance(attacker.tile, other.tile)
            if d <= self.cfg.kill_distance:
                targets.append(other)
        return targets

    async def _kill_player(self, victim: PlayerState, killer: PlayerState):
        victim.is_active = False
        witnesses = [p.name for p in self._get_active_players()
                     if p.agent_id not in (victim.agent_id, killer.agent_id)
                     and self.map.distance(victim.tile, p.tile) <= self.cfg.witness_distance]
        self._game_kills += 1
        self._player_kills[killer.agent_id] = self._player_kills.get(killer.agent_id, 0) + 1
        self.recent_events.append(
            {"type": "kill", "victim": victim.name, "killer": killer.name,
             "witnesses": witnesses})
        await self._emit("combat", "kill", {
            "agent_id": victim.agent_id,
            "victim": victim.name, "killer": killer.name,
            "killed_by": killer.agent_id,
            "witnesses": witnesses})
        self._trace("game_event", {"type": "kill", "killer": killer.name,
                                    "victim": victim.name, "witnesses": witnesses})
        print(f"{victim.name} was killed by {killer.name} — witnesses: {witnesses}")

        # Push kill event into all agents' continuous event channel.
        for p in self._get_active_players():
            if p.agent_id == killer.agent_id:
                p.ctx.add("events", f"You killed {victim.name}!")
            elif p.name in witnesses:
                p.ctx.add("events", f"YOU WITNESSED: {killer.name} killed {victim.name}!")
            else:
                p.ctx.add("events", f"{victim.name} was found dead!")

        result = self.check_win_condition()
        if result["game_over"]:
            await self._end_game(result["winner"])
            return
        await self._emit("system", "system_message", {
            "message": f"{victim.name} was found dead! Starting emergency meeting..."})
        await self._start_voting()

    # ── Voting ────────────────────────────────────────────────────────

    async def _start_voting(self):
        print("══════════ VOTING STARTED ══════════")
        self.phase = Phase.VOTING
        self._state_timer = self.cfg.vote_timeout
        self._bump_phase()
        self.vote_choices.clear()
        active = self._get_active_players()
        print(f"VOTING: {len(active)} players must vote ({self.cfg.vote_timeout}s)")
        self.recent_events.append({"type": "voting_started", "players": len(active)})
        await self._emit("voting", "start", {
            "active_players": len(active),
            "active_agent_ids": [p.agent_id for p in active],
            "timeout": int(self.cfg.vote_timeout),
        })
        # Push voting start into all agents' continuous event channel.
        for p in active:
            p.ctx.add("events",
                f"Emergency meeting! Discuss and cast your votes. "
                f"You have {int(self.cfg.vote_timeout)} seconds.")

    async def _finalize_voting(self):
        if self.phase != Phase.VOTING:
            return
        print(f"VOTING: Finalizing — {len(self.vote_choices)} votes cast")
        totals: dict[str, int] = {}
        for t in self.vote_choices.values():
            totals[t] = totals.get(t, 0) + 1
        tally_strs = [f"{n} ({c})" for n, c in totals.items()]
        tally_msg = ", ".join(tally_strs) if tally_strs else "no votes cast"
        await self._emit("system", "system_message", {"message": f"Vote results: {tally_msg}"})
        if not totals:
            await self._resume_playing(); return

        max_votes = max(totals.values())
        winners = [n for n, c in totals.items() if c == max_votes]
        if len(winners) != 1:
            await self._emit("system", "system_message",
                             {"message": "Vote tied. Nobody was ejected."})
            await self._resume_playing(); return

        voted_name = winners[0]
        if voted_name == "skip":
            await self._emit("system", "system_message",
                             {"message": "Players chose to skip."})
            await self._resume_playing(); return

        victim = next((p for p in self.players.values()
                       if p.name == voted_name and p.is_active), None)
        if victim:
            victim.is_active = False
            self._game_ejections += 1
            self.recent_events.append(
                {"type": "eject", "agent_id": victim.agent_id,
                 "victim": victim.name, "role": victim.agent_type_name})
            await self._emit("system", "system_message",
                             {"message": f"{victim.name} was ejected!"})
            # Push ejection into all players' continuous event channel.
            role_note = f" (was {victim.agent_type_name})"
            for p in self.players.values():
                p.ctx.add("events", f"{victim.name} was ejected!{role_note}")
            await self._emit("voting", "result", {
                "agent_id": victim.agent_id,
                "ejected": victim.name, "role": victim.agent_type_name,
                "vote_tallies": tally_strs})
            if self.check_win_condition()["game_over"]:
                await self._end_game(self.check_win_condition()["winner"])
                self.vote_choices.clear(); return
        self.vote_choices.clear()
        await self._resume_playing()

    async def _resume_playing(self):
        self.phase = Phase.PLAYING
        self._bump_phase()
        self.vote_choices.clear()
        self.recent_events.clear()
        print("══════════ VOTING ENDED — returning to PLAYING ══════════")
        await self._emit("system", "phase_change", {"phase": "playing", "countdown_sec": 0})

    # ── Game lifecycle ────────────────────────────────────────────────

    async def _start_game(self):
        if not self.players:
            return
        self._game_index += 1
        self.phase = Phase.PLAYING
        self._game_timer = self.cfg.game_max_length
        self.recent_events.clear()
        self._game_kills = 0
        self._game_ejections = 0
        self._player_kills.clear()
        self._bump_phase()
        self._game_started_at = datetime.now(timezone.utc).isoformat()
        self._game_started_at_ts = time.time()
        self.events.start_game()
        gid = self.events.game_id
        print(f"Game {gid} Starting!")
        # Open per-game trace file and export config
        if self.events.session_id:
            game_trace_dir = os.path.join(self.events.log_dir, self.events.session_id, gid)
            os.makedirs(game_trace_dir, exist_ok=True)
            game_trace_path = os.path.join(game_trace_dir, "trace.jsonl")
            self._game_trace_file = open(game_trace_path, "w", encoding="utf-8")
            # Export per-game config (may differ per game index)
            if self._experiment_config:
                game_config = dict(self._experiment_config)
                game_config["game_index"] = self._game_index
                config_path = os.path.join(game_trace_dir, "config.json")
                with open(config_path, "w") as cf:
                    json.dump(game_config, cf, indent=2)
        self._trace("game_event", {"type": "game_start", "game_id": gid})

        active_ids = list(self.players.keys())

        # Build agent groups from configured types
        self._groups.clear()
        if not self._agent_types:
            raise RuntimeError("No agent types configured — cannot build agent groups")
        for at in self._agent_types:
            self._groups[at.id] = AgentGroup(name=at.id, _engine=self)

        # Assign players to agent types based on configured counts
        type_assignments: list[str] = []
        for at in self._agent_types:
            type_assignments.extend([at.id] * at.count)
        if len(type_assignments) < len(active_ids):
            # Fallback: pad with first agent type
            fallback = self._agent_types[0].id
            type_assignments.extend([fallback] * (len(active_ids) - len(type_assignments)))
        random.shuffle(type_assignments)

        player_list = []
        for pi, pid in enumerate(active_ids):
            p = self.players[pid]
            p.agent_type_name = type_assignments[pi]
            p.is_active = True
            p.first_time = True
            p.tile = self.map.random_walkable_tile()
            # Initialise context manager — use AgentType config
            at = next((t for t in self._agent_types if t.id == p.agent_type_name), None)
            p.ctx = ContextManager(p.name)
            p.ctx.set_constant("system", BASE_PROMPT)
            if at and at.prompt:
                p.ctx.set_constant("role", at.prompt)
            if at and at.context_manager and at.context_manager.base_prompt:
                p.ctx.set_constant("system", at.context_manager.base_prompt)
            p.agent.set_intro(BASE_PROMPT)
            p.agent.tokens.reset()
            player_list.append({
                "agent_id": p.agent_id, "name": p.name,
                "tile": list(p.tile), "color_index": p.color_index})

        await self._emit("system", "game_start", {"game_id": gid, "players": player_list})
        await self._emit("system", "phase_change",
                         {"phase": "playing", "countdown_sec": self.cfg.game_max_length})

        # Print role assignments
        by_type: dict[str, list[str]] = {}
        for p in self.players.values():
            by_type.setdefault(p.agent_type_name, []).append(p.name)
        for tname, names in by_type.items():
            print(f"[{tname}]: {names}")

    async def _end_game(self, reason: str):
        msgs = {"timeout": "Game Over! Time limit reached.",
                "token_limit": "Game Over! Token budget exceeded."}
        msg = msgs.get(reason, f"Game Over! {reason} win!")
        print(msg)
        self._trace("game_event", {"type": "game_end", "winner": reason})
        await self._emit("system", "system_message", {"message": msg})
        now_ts = datetime.now(timezone.utc).isoformat()
        recap = {
            "schema_version": "1.0",
            "session_id": self.events.session_id,
            "game_id": self.events.game_id,
            "started_at": getattr(self, "_game_started_at", None),
            "ended_at": now_ts,
            "duration_sec": time.time() - getattr(self, "_game_started_at_ts", time.time()),
            "winner": reason, "kills": self._game_kills,
            "ejections": self._game_ejections,
            "players": [{"name": p.name, "role": p.agent_type_name,
                         "alive": p.is_active,
                         "kills": self._player_kills.get(p.agent_id, 0),
                         "color": self.cfg.agent_colors[p.color_index % len(self.cfg.agent_colors)]}
                        for p in self.players.values()],
        }
        for p in self.players.values():
            p.is_active = False
        await self._emit("system", "game_end", {"winner": reason, "recap": recap})
        self.events.end_game(recap)
        # Close per-game trace
        if self._game_trace_file:
            self._game_trace_file.close()
            self._game_trace_file = None
        # Accumulate recap for run() summary
        self._recaps.append(recap)
        await self._start_starting()

    async def _start_starting(self):
        self.phase = Phase.STARTING
        self._state_timer = self.cfg.start_countdown
        self._bump_phase()
        await self._emit("system", "phase_change",
                         {"phase": "starting", "countdown_sec": self.cfg.start_countdown})

    # ── Main game loop ────────────────────────────────────────────────

    async def run(self, max_games: Optional[int] = None) -> dict:
        print("[Engine] Starting...")
        self.events.start_session()
        # Send map data to both logs and Godot so the renderer can initialise
        await self._emit("system", "map_data", self.map.serialize())
        # Also log the experiment config as a system event
        if self._experiment_config:
            self.events.log_event("system", "config", self._experiment_config)
        self._open_trace()

        if self.render:
            await self.render.reconnect_loop()
        else:
            print("[Engine] Headless mode — no Godot renderer")

        self._seed_players()

        await self._emit("system", "system_message",
                         {"message": "Engine connected. Waiting for agents..."})
        await self._emit("system", "phase_change",
                         {"phase": "starting", "countdown_sec": self.cfg.start_countdown})

        await self._start_starting()
        last_tick_time = time.time()
        summary = {}

        try:
            while True:
                now = time.time()
                dt = now - last_tick_time
                last_tick_time = now
                self._tick += 1

                if self.phase == Phase.PLAYING:
                    self._game_timer -= dt
                elif self.phase in (Phase.STARTING, Phase.VOTING):
                    self._state_timer -= dt

                if self.phase == Phase.STARTING:
                    if self._state_timer <= 0:
                        if max_games is not None and self._game_index >= max_games:
                            print(f"[Engine] Reached max_games ({max_games}) — stopping")
                            summary = self._build_summary()
                            break
                        await self._start_game()
                elif self.phase == Phase.PLAYING:
                    if self._game_timer <= 0:
                        result = self.check_win_condition()
                        await self._end_game(
                            result["winner"] if result["game_over"] else "timeout")
                    else:
                        await self._tick_playing()
                elif self.phase == Phase.VOTING:
                    if self._state_timer <= 0:
                        await self._finalize_voting()
                    else:
                        sec = int(self._state_timer)
                        if sec != self._last_vote_log_second and sec % 10 == 0:
                            active_count = len(self._get_active_players())
                            print(f"VOTING: {sec}s remaining, "
                                  f"{len(self.vote_choices)}/{active_count} votes")
                        self._last_vote_log_second = sec
                        await self._tick_voting()

                self.events.tick()
                if self.render:
                    await self.render.send_heartbeat()

                elapsed = time.time() - now
                await asyncio.sleep(max(0.1, self.cfg.agent_tick_interval - elapsed))

        except KeyboardInterrupt:
            print("\n[Engine] Interrupted — shutting down...")
            summary = self._build_summary()
        finally:
            self.events.end_session()
            self._close_trace()
            if self.render:
                await self.render.close()
            print("[Engine] Stopped.")
        return summary

    def _build_summary(self) -> dict:
        """Build a summary dict from accumulated recaps."""
        by_winner: dict[str, int] = {}
        total_kills = 0
        total_ejections = 0
        for g in self._recaps:
            w = g.get("winner", "unknown")
            if w in by_winner:
                by_winner[w] += 1
            total_kills += g.get("kills", 0)
            total_ejections += g.get("ejections", 0)
        return {
            "session_id": self.events.session_id,
            "games": len(self._recaps),
            "total_kills": total_kills,
            "total_ejections": total_ejections,
            "by_winner": by_winner,
            "recaps": self._recaps,
        }

    async def _tick_playing(self):
        active = self._get_active_players()
        if not active:
            return

        if self._token_budget_exceeded():
            await self._end_game("token_limit")
            return

        decisions = await self._ask_agents(active, is_voting=False)
        for p in active:
            decision = decisions.get(p.agent_id, {})
            if not decision:
                continue
            if decision.get("phase_id") != self._phase_id:
                if VERBOSE:
                    print(f"Voiding stale response from {p.name}")
                continue
            await self._process_playing_action(p, decision)

    async def _tick_voting(self):
        active = self._get_active_players()
        if self._token_budget_exceeded():
            await self._end_game("token_limit")
            return

        pending = [p for p in active if p.agent_id not in self.vote_choices]
        elapsed = self.cfg.vote_timeout - self._state_timer
        can_finalize = elapsed >= self.cfg.min_vote_time

        if not pending:
            if len(self.vote_choices) >= len(active) and can_finalize:
                print("VOTING: All voted — finalizing early!")
                await self._finalize_voting()
            return

        decisions = await self._ask_agents(pending, is_voting=True)
        for p in pending:
            decision = decisions.get(p.agent_id, {})
            if not decision or decision.get("phase_id") != self._phase_id:
                continue
            await self._process_voting_action(p, decision)

        if len(self.vote_choices) >= len(active) and can_finalize:
            print("VOTING: All voted — finalizing early!")
            await self._finalize_voting()

    def _seed_players(self):
        n = self.cfg.player_count
        persona_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "personas")
        personas = load_personas(persona_dir, n)
        for i in range(n):
            name = self.cfg.agent_names[i % len(self.cfg.agent_names)]
            agent = Agent(persona=personas[i], name=name)
            agent.tokens.limit = self.cfg.token_limit
            self.players[i] = PlayerState(
                agent_id=i, name=name, agent=agent,
                tile=self.map.random_walkable_tile(),
                color_index=i % len(self.cfg.agent_colors), index=i)
        print(f"[Engine] {n} players ready (token budget: {self.cfg.token_limit})")


# ── Entry point ───────────────────────────────────────────────────────────

async def main():
    import argparse
    p = argparse.ArgumentParser(description="Among-I Python Game Engine")
    p.add_argument("--render", action="store_true",
                   help="Connect to Godot renderer on :8081")
    p.add_argument("--render-host", default="localhost")
    p.add_argument("--render-port", type=int, default=8081)
    p.add_argument("--map", default=None, help="Path to map JSON (default: built-in square platform)")
    p.add_argument("--log-dir", default="../log")
    p.add_argument("--max-games", type=int, default=None, help="Stop after N games (default: run forever)")
    args = p.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    config = GameConfig()

    if args.map:
        map_data = FileMap(os.path.join(base, args.map))
    else:
        map_data = SquareMap(16)
    log_dir = os.path.abspath(os.path.join(base, args.log_dir))
    event_store = EventStore(log_dir=log_dir)
    print(f"[Engine] Logs: {log_dir}")

    render_client = None
    if args.render:
        render_client = RenderClient(args.render_host, args.render_port)

    engine = GameEngine(config, map_data, event_store, render_client, [])
    summary = await engine.run(max_games=args.max_games)
    print(f"[Engine] Summary: {json.dumps(summary, indent=2) if summary else 'none'}")


if __name__ == "__main__":
    asyncio.run(main())
