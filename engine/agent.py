#!/usr/bin/env python3
"""agent.py — LLM agent class imported directly by the engine.

Each agent instance holds a persona, LLM conversation history, and token
tracker. The engine calls agent.think(context) to get decisions synchronously
(blocking call run in a thread).

Usage (from engine.py):
    from agent.agent import Agent
    agent = Agent(persona="You are...")
    decision = await agent.think(context_dict)
"""

import json
import os
import time
import dataclasses
from typing import Optional

import dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, ConfigDict, create_model

dotenv.load_dotenv()

MODEL = os.getenv("MODEL", "gpt-5.4-mini").strip()
OPEN_ROUTER_API_KEY = os.getenv("OPEN_ROUTER_API_KEY", "")
TOKEN_LIMIT = int(os.getenv("TOKEN_LIMIT", "100000"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))
VERBOSE = os.getenv("VERBOSE", "0").strip() == "1"

# Shared LLM client — no SDK-level retries (a hung request would stall the
# whole engine loop; the per-call timeout bounds each decision instead).
_llm = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPEN_ROUTER_API_KEY,
    max_retries=0,
)


# ── Token Tracking ────────────────────────────────────────────────────────

@dataclasses.dataclass
class TokenUsageLog:
    timestamp: float
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    agent_name: str = "unknown"


class TokenBudgetExceeded(Exception):
    pass


class TokenTracker:
    def __init__(self, limit: int = TOKEN_LIMIT):
        self.limit = limit
        self.total_used: int = 0
        self.log: list[TokenUsageLog] = []

    def reset(self):
        """Reset cumulative counters (called at game start)."""
        self.total_used = 0
        self.log = []

    def record(self, completion, agent_name: str) -> TokenUsageLog:
        usage = completion.usage
        entry = TokenUsageLog(
            timestamp=time.time(), model=completion.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens, agent_name=agent_name)
        self.log.append(entry)
        self.total_used += entry.total_tokens
        print(f"[TOKEN] {agent_name} | prompt={entry.prompt_tokens} "
              f"completion={entry.completion_tokens} total={entry.total_tokens} "
              f"cumulative={self.total_used}/{self.limit}")
        if self.total_used >= self.limit:
            raise TokenBudgetExceeded(
                f"Budget exceeded: {self.total_used} >= {self.limit}")
        return entry


# ── Dynamic Schema Generation ─────────────────────────────────────────────

def make_strict(schema: dict):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
        for value in schema.values():
            make_strict(value)
    elif isinstance(schema, list):
        for item in schema:
            make_strict(item)


TYPE_MAP = {"integer": int, "number": float, "string": str, "boolean": bool}


def get_action_model(schema: dict) -> type[BaseModel]:
    config = ConfigDict(extra="forbid")
    fields = {}
    for prop_name, definition in schema.get("properties", {}).items():
        py_type = TYPE_MAP.get(definition.get("type", "string"), str)
        fields[prop_name] = (py_type, Field(description=definition.get("description", "")))
    model = create_model("DynamicAgentAction", __config__=config, **fields)
    make_strict(model.model_json_schema())
    return model


# ── Agent ─────────────────────────────────────────────────────────────────

class Agent:
    """One LLM-backed agent. Holds persistent conversation history so that
    chats, kills, and game events accumulate naturally across turns."""

    def __init__(self, persona: str, name: str = "?"):
        self.persona = persona
        self.name = name
        self.messages: list[dict] = []       # persistent conversation history
        self.tokens = TokenTracker()
        self.turn: int = 0
        self.last_api_messages: list[dict] = []

    def set_intro(self, intro: str):
        """Set the system intro (called at game start / memory clear)."""
        self.messages = [{"role": "system", "content": intro}]

    def add_message(self, role: str, content: str):
        """Append an event message to the persistent history."""
        self.messages.append({"role": role, "content": content})

    def clear_memory(self):
        """Keep only the system intro message."""
        intro = self.messages[0] if self.messages else None
        self.messages = [intro] if intro else []

    def _trim_history(self, turns: int = 8) -> None:
        """Keep the system prompt + the last N turns (user/assistant pairs)."""
        system = self.messages[0] if self.messages and self.messages[0]["role"] == "system" else None
        rest = [m for m in self.messages if m["role"] != "system"]
        keep = rest[-turns * 2:]
        self.messages = ([system] if system else []) + keep

    def think(self, context: dict) -> dict:
        """Call the LLM and return a decision dict. Synchronous (run in thread)."""
        action_schema = context.get("action_schema", {})
        schema_props = action_schema.get("properties", {})
        is_voting = "vote" in schema_props

        # Empty schema — skip LLM
        if len(schema_props) == 0:
            return {}

        prompt = context.get("prompt", "")
        if not prompt:
            return self._safe_default(is_voting)

        # The system prompt (self.messages[0]) stays FIXED. Per-turn info
        # goes on the stack as a user message, decisions as assistant
        # messages — so outputs sit between the events that caused them.
        self.messages.append({"role": "user", "content": prompt})
        self._trim_history()
        api_messages = list(self.messages)
        self.last_api_messages = api_messages

        try:
            ActionModel = get_action_model(action_schema)
            completion = _llm.chat.completions.create(
                model=MODEL, messages=api_messages,
                timeout=LLM_TIMEOUT,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "agent_action",
                        "schema": ActionModel.model_json_schema(),
                        "strict": True,
                    },
                },
            )

            self.tokens.record(completion, agent_name=self.name)

            content = str(completion.choices[0].message.content)
            try:
                decision = ActionModel.model_validate_json(content).model_dump()
            except Exception:
                import re
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    decision = ActionModel.model_validate_json(match.group()).model_dump()
                else:
                    raise

            # Append decision to persistent history
            self.messages.append({"role": "assistant", "content": json.dumps(decision)})
            self._trim_history()
            return decision

        except TokenBudgetExceeded:
            print(f"[{self.name}] Token budget exceeded — idling")
            return self._safe_default(is_voting)
        except Exception as e:
            print(f"[{self.name}] LLM error: {e}")
            return self._safe_default(is_voting)

    def _safe_default(self, is_voting: bool) -> dict:
        if is_voting:
            return {"vote": "skip", "chat": ""}
        return {"move_x": 0, "move_y": 0, "chat": "", "reason": "Error — idling"}
