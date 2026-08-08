"""context_manager.py — Builds and manages agent context as typed channels.

Three channel types:
  - CONSTANT:  System prompt + role instructions — set once, always at the top.
  - CONTINUOUS: Events that accumulate each tick (kills, chats, ejections).
  - TEMPORARY:  Per-turn context (world view, nearby bots) — shown only this tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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


class ContextManager:
    """Manages typed channels that combine into an agent's prompt context.

    Channels are rendered in order: CONSTANT → CONTINUOUS → TEMPORARY.
    CONTINUOUS items persist across ticks (like chat history).
    TEMPORARY items are cleared each tick after the prompt is built.
    """

    def __init__(self, agent_name: str, is_imposter: bool = False):
        self.agent_name = agent_name
        self.is_imposter = is_imposter
        self.first_turn = True
        self.channels: dict[str, ContextChannel] = {}

    def add_channel(self, name: str, ctype: ChannelType):
        self.channels[name] = ContextChannel(name=name, ctype=ctype)

    def add(self, channel: str, item: str):
        if channel not in self.channels:
            self.add_channel(channel, ChannelType.CONTINUOUS)
        self.channels[channel].add(item)

    def set_constant(self, channel: str, content: str):
        """Set a constant channel — replaces any previous value."""
        if channel not in self.channels:
            self.add_channel(channel, ChannelType.CONSTANT)
        ch = self.channels[channel]
        ch.items = [content]
        ch.ctype = ChannelType.CONSTANT

    def set_temporary(self, channel: str, content: str):
        """Set temporary context for this tick only."""
        if channel not in self.channels:
            self.add_channel(channel, ChannelType.TEMPORARY)
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

    def build_messages(self) -> list[dict]:
        """Build API messages from channels."""
        prompt = self.build_prompt()
        if not prompt:
            return []
        return [{"role": "system", "content": prompt}]
