#!/usr/bin/env python3
"""index.py — LLM agent process for Among-I.

Connects to the game engine via WebSocket, receives context packets,
calls the LLM (OpenRouter), and returns structured decisions.

One process can run multiple agents concurrently (--count N). Each agent
gets an independent WebSocket connection, persona, and LLM conversation.

Usage:
    # Run 5 agents in a single process (connect to engine on default port):
    python index.py --count 5

    # Run a single agent with a specific persona:
    python index.py --persona CowboyJack.txt --engine-port 8080
"""

import asyncio
import json
import glob
import os
import random
import sys
import time
import dataclasses
from typing import Optional

import dotenv
import websockets
from openai import OpenAI
from pydantic import BaseModel, Field, ConfigDict, create_model


# ── Configuration ─────────────────────────────────────────────────────────

dotenv.load_dotenv()

MODEL = os.getenv("MODEL", "google/gemini-2.5-flash").strip()
OPEN_ROUTER_API_KEY = os.getenv("OPEN_ROUTER_API_KEY", "")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))
TOKEN_LIMIT = int(os.getenv("TOKEN_LIMIT", "100000"))
VERBOSE = os.getenv("VERBOSE", "0").strip() == "1"


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


# ── Shared LLM client (thread-safe) ───────────────────────────────────────

_llm_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPEN_ROUTER_API_KEY,
)


# ── Persona Loading ───────────────────────────────────────────────────────

def load_persona(folder: str = "personas", name: Optional[str] = None) -> str:
    if name:
        fp = os.path.join(folder, name)
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return f.read().strip()
    files = glob.glob(os.path.join(folder, "*.txt"))
    if not files:
        return "You are a generic helpful bot."
    return open(random.choice(files), "r", encoding="utf-8").read().strip()


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


# ── LLM Call ──────────────────────────────────────────────────────────────

def call_llm(prompt: str, action_schema: dict, messages: list[dict],
             token_tracker: TokenTracker, agent_name: str) -> dict:
    api_messages = [{"role": "system", "content": prompt}]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    api_messages.extend(assistant_msgs[-5:])

    ActionModel = get_action_model(action_schema)

    completion = _llm_client.chat.completions.create(
        model=MODEL, messages=api_messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "agent_action",
                "schema": ActionModel.model_json_schema(),
                "strict": True,
            },
        },
    )

    token_tracker.record(completion, agent_name=agent_name)
    content = str(completion.choices[0].message.content)
    # Robust parsing: strip trailing garbage (LLMs sometimes append extra chars)
    try:
        return ActionModel.model_validate_json(content).model_dump()
    except Exception:
        # Try to find and parse just the first JSON object
        import re
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return ActionModel.model_validate_json(match.group()).model_dump()
        raise


def safe_default(is_voting: bool) -> dict:
    return ({"vote": "skip", "chat": ""} if is_voting
            else {"move_x": 0, "move_y": 0, "chat": "", "reason": "Error — idling"})


# ── Single Agent Loop ─────────────────────────────────────────────────────

async def agent_loop(engine_uri: str, persona: str, agent_index: int):
    """One agent: connect to engine, receive context, call LLM, return decisions."""
    token_tracker = TokenTracker()
    messages: list[dict] = []
    turn = 0
    agent_name = "?"

    # Connect with retry (engine may still be starting)
    ws_conn = None
    for attempt in range(10):
        try:
            ws_conn = await websockets.connect(engine_uri)
            break
        except (OSError, websockets.exceptions.InvalidURI,
                websockets.exceptions.InvalidHandshake):
            if attempt == 9:
                print(f"[Agent {agent_index}] Cannot reach engine at {engine_uri}"
                      f" — giving up")
                return
            print(f"[Agent {agent_index}] Waiting for engine ({attempt+1}/10)...")
            await asyncio.sleep(1.0)

    try:
        async with ws_conn as ws:
            print(f"[Agent {agent_index}] Connected to engine")

            while True:
                raw = await ws.recv()
                game_data = json.loads(raw)

                agent_name = game_data.get("name", "?")
                is_idle = game_data.get("is_idle", False)
                phase_id = game_data.get("phase_id", 0)

                if is_idle:
                    await ws.send(json.dumps({}))
                    turn += 1
                    continue

                if game_data.get("clear_memory", False):
                    messages = []

                action_schema = game_data.get("action_schema", {})
                schema_props = action_schema.get("properties", {})
                is_voting = "vote" in schema_props
                is_empty = len(schema_props) == 0

                if is_empty:
                    await ws.send(json.dumps({"phase_id": phase_id}))
                    turn += 1
                    continue

                prompt = game_data.get("prompt", "")
                if not prompt:
                    await ws.send(json.dumps({"phase_id": phase_id}))
                    turn += 1
                    continue

                # Log events
                for ev in game_data.get("events", []):
                    etype = ev.get("type", "")
                    if etype == "kill":
                        print(f"[{agent_name}] {ev.get('victim')} was killed!")
                    elif etype == "eject":
                        print(f"[{agent_name}] {ev.get('victim')} was ejected")
                    elif etype == "voting_started":
                        print(f"[{agent_name}] Emergency meeting! {ev.get('players')} voting")

                status = "VOTING" if is_voting else "PLAYING"
                print(f"[{agent_name}] Turn {turn} | {status} | imposter={game_data.get('is_imposter', False)}")

                # Call LLM
                try:
                    decision = await asyncio.to_thread(
                        call_llm, prompt=prompt, action_schema=action_schema,
                        messages=messages, token_tracker=token_tracker,
                        agent_name=agent_name)
                except TokenBudgetExceeded:
                    decision = safe_default(is_voting)
                except Exception as e:
                    print(f"[{agent_name}] LLM error: {e}")
                    decision = safe_default(is_voting)

                messages.append({"role": "assistant", "content": json.dumps(decision)})

                if is_voting:
                    if "vote" not in decision:
                        decision["vote"] = "skip"
                    print(f"[{agent_name}] VOTED: {decision['vote']}")
                elif VERBOSE:
                    print(f"[{agent_name}] move=({decision.get('move_x', 0)},{decision.get('move_y', 0)}) "
                          f"chat=\"{str(decision.get('chat', ''))[:40]}\"")

                decision["phase_id"] = phase_id
                await ws.send(json.dumps(decision))
                turn += 1

    except websockets.exceptions.ConnectionClosed:
        print(f"[Agent {agent_index}] ({agent_name}) Engine connection closed.")
    except Exception as e:
        print(f"[Agent {agent_index}] ({agent_name}) Fatal error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="Among-I LLM Agent")
    p.add_argument("--engine-host", default="localhost")
    p.add_argument("--engine-port", type=int, default=8080)
    p.add_argument("--count", type=int, default=1, metavar="N",
                   help="Number of agents to run concurrently (default: 1)")
    p.add_argument("--persona", default=None,
                   help="Specific persona file (default: random for each agent)")
    p.add_argument("--persona-dir", default="personas")
    args = p.parse_args()

    uri = f"ws://{args.engine_host}:{args.engine_port}"

    # Resolve persona directory relative to this script
    base = os.path.dirname(os.path.abspath(__file__))
    persona_dir = os.path.join(base, args.persona_dir)

    print(f"Agent runner — engine: {uri}  count: {args.count}")

    # Build agent tasks
    async def run_all():
        tasks = []
        for i in range(args.count):
            # Each agent gets its own persona (random unless --persona given)
            persona = load_persona(persona_dir, args.persona)
            persona_preview = persona[:60].replace("\n", " ")
            print(f"  Agent {i}: {persona_preview}...")
            tasks.append(asyncio.create_task(
                agent_loop(uri, persona, i)))

        # Run all concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"  Agent {i} exited with error: {r}")

    asyncio.run(run_all())


if __name__ == "__main__":
    main()
