"""context_manager.py — Builds and manages agent context as typed channels.

Three channel types:
  - CONSTANT:  System prompt + role instructions — set once, always at the top.
  - CONTINUOUS: Events that accumulate each tick (kills, chats, ejections).
  - TEMPORARY:  Per-turn context (world view, nearby bots) — shown only this tick.

ContextManager is an ExperimentComponent so channels can be declared in config
and wired to agent types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from experiment import ExperimentComponent, Param


class ChannelType(Enum):
    CONSTANT = "constant"
    CONTINUOUS = "continuous"
    TEMPORARY = "temporary"


@dataclass
class ContextChannel:
    name: str
    ctype: ChannelType
    items: list[str] = field(default_factory=list)

    def add(self, item: str):
        self.items.append(item)

    def clear(self):
        self.items.clear()


class ContextManager(ExperimentComponent):
    """Configurable context builder — defines channels and prompt templates
    for building agent context. One per agent type; the engine creates
    runtime copies per agent from this template."""

    component_type = "ContextManager"
    params = {
        "base_prompt": Param(str, "", "Base system prompt for all agents"),
        "channels": Param(list, [], "Channel definitions [{name, ctype}]"),
    }
    exposes = {
        "variables": {},
        "functions": {
            "build_prompt": {"args": [], "returns": "str",
                           "desc": "Build the full prompt from all channels"},
            "build_messages": {"args": [], "returns": "list[dict]",
                             "desc": "Build API-compatible messages from channels"},
        },
    }

    def __init__(self, agent_name: str = "", **kwargs):
        # Pull config params from kwargs before passing to ExperimentComponent
        cfg_channels = kwargs.pop("channels", None) or []
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self.first_turn = True
        self.channels: dict[str, ContextChannel] = {}
        self._sent: dict[str, int] = {}   # per-channel cursor of sent items

        # Apply config channels if provided
        for ch_def in cfg_channels:
            ctype_str = ch_def.get("ctype", "continuous")
            ctype = ChannelType.CONTINUOUS
            if ctype_str == "constant":
                ctype = ChannelType.CONSTANT
            elif ctype_str == "temporary":
                ctype = ChannelType.TEMPORARY
            ch = self._add_channel(ch_def.get("name", ""), ctype)
            if ch_def.get("content"):
                if ctype == ChannelType.CONSTANT:
                    ch.items = [ch_def["content"]]
                elif ctype == ChannelType.TEMPORARY:
                    ch.items = [ch_def["content"]]

    def _add_channel(self, name: str, ctype: ChannelType) -> ContextChannel:
        ch = ContextChannel(name=name, ctype=ctype)
        self.channels[name] = ch
        return ch

    def add(self, channel: str, item: str):
        if channel not in self.channels:
            self._add_channel(channel, ChannelType.CONTINUOUS)
        self.channels[channel].add(item)

    def set_constant(self, channel: str, content: str):
        """Set a constant channel — replaces any previous value."""
        if channel not in self.channels:
            self._add_channel(channel, ChannelType.CONSTANT)
        ch = self.channels[channel]
        ch.items = [content]
        ch.ctype = ChannelType.CONSTANT

    def set_temporary(self, channel: str, content: str):
        """Set temporary context for this tick only."""
        if channel not in self.channels:
            self._add_channel(channel, ChannelType.TEMPORARY)
        ch = self.channels[channel]
        ch.items = [content]
        ch.ctype = ChannelType.TEMPORARY

    def build_prompt(self) -> str:
        """Build the full prompt from all channels in order."""
        parts = []

        # CONSTANT channels first
        for ch in self.channels.values():
            if ch.ctype == ChannelType.CONSTANT and ch.items:
                parts.append(ch.items[0])

        # CONTINUOUS channels in the middle
        for ch in self.channels.values():
            if ch.ctype == ChannelType.CONTINUOUS and ch.items:
                header = f"\n{ch.name}:\n"
                body = "\n".join(f"- {item}" for item in ch.items[-50:])
                parts.append(header + body)

        # TEMPORARY channels last
        for ch in self.channels.values():
            if ch.ctype == ChannelType.TEMPORARY and ch.items:
                parts.append(ch.items[0])

        # Clear temporary channels after building
        for ch in self.channels.values():
            if ch.ctype == ChannelType.TEMPORARY:
                ch.clear()

        return "\n\n".join(parts)

    def build_system_prompt(self) -> str:
        """The FIXED system prompt — CONSTANT channels only. Sent once at
        game start and never rebuilt; per-turn info goes in user messages."""
        parts = []
        for ch in self.channels.values():
            if ch.ctype == ChannelType.CONSTANT and ch.items:
                parts.append(ch.items[0])
        return "\n\n".join(parts)

    def build_user_message(self) -> str:
        """Per-turn info as a conversation user message.

        Only NEW items since the last call are included (continuous
        channels keep a per-channel cursor), and temporary channels are
        cleared after being sent. Constants are excluded — they live in
        the fixed system prompt."""
        parts = []
        for name, ch in self.channels.items():
            if ch.ctype == ChannelType.CONSTANT or not ch.items:
                continue
            if ch.ctype == ChannelType.CONTINUOUS:
                new_items = ch.items[self._sent.get(name, 0):]
                if new_items:
                    parts.append(f"{name}:\n" + "\n".join(f"- {item}" for item in new_items))
                self._sent[name] = len(ch.items)
            elif ch.ctype == ChannelType.TEMPORARY:
                if ch.items:
                    parts.append(ch.items[0])
                ch.clear()
        return "\n\n".join(parts)

    def build_messages(self) -> list[dict]:
        """Build API messages from channels."""
        prompt = self.build_prompt()
        if not prompt:
            return []
        return [{"role": "system", "content": prompt}]

    def description(self) -> str:
        return f"context manager ({len(self.channels)} channels)"


# ── ChatContext ──────────────────────────────────────────────────────────


class ChatContext(ExperimentComponent):
    """Encapsulates chat message routing between agents.

    Handles proximity-based delivery, global chat history, and broadcast
    behaviour. One instance per engine; routes chat from any agent to
    nearby agents via their :class:`ContextManager` channels.

    Config params:
        chat_distance: max tiles for a message to reach another agent.
                       Default is very large (10000), making chat global.
    """

    component_type = "ChatContext"
    params = {
        "chat_distance": Param(float, 10000.0, "Max tiles for chat delivery"),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.recent_global_chats: list[str] = []

    def route(self, engine, player, message: str,
              broadcast: bool = False) -> dict | None:
        """Route a chat message from *player* to nearby agents.

        Appends to each recipient's ``chat`` channel (via
        :meth:`ContextManager.add`) and to the global chat log.
        Returns the action dict for logging (does NOT emit events).

        Args:
            engine: The :class:`GameEngine` instance (provides map +
                    ``_get_active_players()``).
            player: The sending :class:`PlayerState`.
            message: The chat text.
            broadcast: If True, deliver to all active players regardless
                       of distance (used during voting).
        """
        if not message:
            return None
        chat_line = f"{player.name}: {message}"
        self.recent_global_chats.append(chat_line)
        action = {
            "type": "say",
            "message": message,
            "broadcast": broadcast,
            "pos": {"x": player.tile.x, "y": player.tile.y},
        }
        for other in engine._get_active_players():
            if other.agent_id == player.agent_id:
                continue
            if engine.map.distance(player.tile, other.tile) <= self.chat_distance or broadcast:
                dx = player.tile.x - other.tile.x
                dy = other.tile.y - player.tile.y  # Y-up for display
                other.ctx.add("chat", f"{chat_line}  (dx={dx:+d}, dy={dy:+d})")
        return action

    def description(self) -> str:
        return f"chat context (distance={self.chat_distance}, {len(self.recent_global_chats)} messages)"
