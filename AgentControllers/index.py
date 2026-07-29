import asyncio
import json
import glob
import random
import os
import websockets
from dotenv import load_dotenv
from typing import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field, ConfigDict
from langchain_openai import ChatOpenAI
from openai import OpenAI
import dataclasses, time

from pydantic import create_model, Field
# Load variables from .env
load_dotenv()

# Load example response for shaping prompts and coercion
# EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), "example_response.json")

EXAMPLE_RESPONSE = {"move": "idle", "chat": "", "reason": ""}

# Model provider switch: 'google' (default) or 'openai'
MODEL = os.getenv("MODEL", "google").strip().lower()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))
VERBOSE = os.getenv("VERBOSE", "0").strip() == "1"

def load_random_personalities(folder_path: str, count: int):
    # 1. Find all .txt files in the folder
    search_pattern = os.path.join(folder_path, "*.txt")
    all_files = glob.glob(search_pattern)
    
    if not all_files:
        print(f"No personality files found in {folder_path}!")
        return ["You are a generic helpful bot."] # Fallback

    # 2. Pick a random sample (don't exceed the number of files available)
    num_to_pick = min(count, len(all_files))
    selected_files = random.sample(all_files, num_to_pick)
    
    personalities = []
    for file_path in selected_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            # We use the filename as a label and the content as the prompt
            content = f.read().strip()
            personalities.append(content)
            
    return personalities

def make_strict(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
        for value in schema.values():
            make_strict(value)
    elif isinstance(schema, list):
        for item in schema:
            make_strict(item)

def get_action_model_from_schema(schema):
    config = ConfigDict(extra='forbid')
    fields = {}
    type_map = {
        "integer": int,
        "number": float,
        "string": str,
        "boolean": bool,
    }

    for name, definition in schema.get("properties", {}).items():
        prop_type = definition.get("type", "string")
        py_type = type_map.get(prop_type, str)
        fields[name] = (py_type, Field(description=definition.get("description", "")))

    model = create_model(
        "DynamicAgentAction",
        __config__=config,
        **fields
    )
    make_strict(model.model_json_schema())
    return model

# 1. Define the AI's "Brain" State
class AgentState(TypedDict):
    game_data: dict
    decision: dict
    personality: str
    first_time: bool
    messages: list
    is_imposter: bool

uri = "ws://localhost:8080"


client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=os.getenv("OPEN_ROUTER_API_KEY")
)


# TOKEN TRACKING
@dataclasses.dataclass
class TokenUsageLog:
    timestamp: float
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    agent_name: str = "unknown"

class TokenBudgetExceeded(Exception):
    """Raised when cumulative token usage exceeds the configured limit."""
    pass

class TokenTracker:
    """
    Accumulates token usage across calls.
    TOKEN_LIMIT env var sets the max total tokens (default 100_000).
    When exceeded, raises TokenBudgetExceeded.
    """
    def __init__(self):
        self.limit: int = int(os.getenv("TOKEN_LIMIT", "100000"))
        self.total_used: int = 0
        self.log: list[TokenUsageLog] = []

    def record(
        self,
        completion,           # raw OpenAI completion object
        agent_name: str,
        chat_log: list[str],  # mutated in-place — appended to game chat log
    ) -> TokenUsageLog:
        usage = completion.usage
        entry = TokenUsageLog(
            timestamp=time.time(),
            model=completion.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            agent_name=agent_name,
        )
        self.log.append(entry)
        self.total_used += entry.total_tokens

        # Append a human-readable line to the in-game chat log 
        summary = (
            f"[TOKEN] {agent_name} | "
            f"prompt={entry.prompt_tokens} "
            f"completion={entry.completion_tokens} "
            f"total={entry.total_tokens} "
            f"cumulative={self.total_used}/{self.limit}"
        )
        chat_log.append(summary)
        print(summary)

        # Halt if over budget 
        if self.total_used >= self.limit:
            msg = (
                f"[TOKEN] Budget exceeded: "
                f"{self.total_used} >= {self.limit}. Halting agent {agent_name}."
            )
            chat_log.append(msg)
            print(msg)
            raise TokenBudgetExceeded(msg)

        return entry

# One shared tracker for all agents in the process
_token_tracker = TokenTracker()

async def think_node(state: AgentState):
    data = state['game_data']

    if data.get("clear_memory", False):
        state["messages"] = []
        print("Memory cleared as per game instruction.")

    prompt = data.get("prompt", "")
    if not prompt:
        raise ValueError("No prompt provided in game_data.")

    action_schema = data.get("action_schema")
    DynamicAction = get_action_model_from_schema(action_schema)

    # Build messages: current system prompt + last N assistant responses only.
    # We do NOT store old system prompts in history — they describe stale
    # world state and duplicate the current prompt, wasting tokens.
    api_messages = [
        {"role": "system", "content": prompt},
    ]
    # Add last 5 assistant responses for conversational continuity
    assistant_msgs = [m for m in state["messages"] if m["role"] == "assistant"]
    api_messages.extend(assistant_msgs[-5:])

    completion = client.chat.completions.create(
        model=MODEL,
        messages=api_messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "agent_action",
                "schema": DynamicAction.model_json_schema(),
                "strict": True
            }
        }
    )

    # TRACK TOKEN USAGE right after API call
    agent_name = state["game_data"].get("name", "agent")
    chat_log = state["game_data"].setdefault("chat_logs", [])

    _token_tracker.record(completion, agent_name=agent_name, chat_log=chat_log)
    # TokenBudgetExceeded propagates up from here if the limit is hit

    response = DynamicAction.model_validate_json(str(completion.choices[0].message.content))
    json_response = response.model_dump_json()

    state["messages"].append({
        "role": "assistant",
        "content": json_response
    })

    return {"decision": json.loads(json_response)}

async def agent_node(game_data, index, personality,):
    input_state: AgentState = {
        "game_data": game_data,
        "decision": {},
        "personality": personality,
        "first_time": index == 0,
        "messages": [],
        "is_imposter": game_data.get("is_imposter", False),
    }

    name = game_data.get("name", "?")
    is_imposter = input_state["is_imposter"]

    # Detect phase and schema info
    action_schema = game_data.get("action_schema", {})
    schema_props = action_schema.get("properties", {})
    is_voting = "vote" in schema_props
    is_empty_schema = len(schema_props) == 0

    # Skip LLM call when schema is empty (near-timeout, waiting for phase end)
    if is_empty_schema:
        print(f"[{name}] Skipping LLM — empty action schema (phase transition / near-timeout)")
        return {}

    # Log game events (kills, ejections, etc.)
    for ev in game_data.get("events", []):
        etype = ev.get("type", "")
        if etype == "kill":
            print(f"[{name}] EVENT: {ev.get('victim')} was killed! Witnesses: {ev.get('witnesses', [])}")
        elif etype == "eject":
            print(f"[{name}] EVENT: {ev.get('victim')} was ejected (was imposter: {ev.get('was_imposter', False)})")
        elif etype == "voting_started":
            print(f"[{name}] EVENT: Emergency meeting! {ev.get('players')} players voting.")

    if VERBOSE:
        print(f"[{name}] Turn {index} | imposter={is_imposter} | voting={is_voting}")
    else:
        status = "VOTING" if is_voting else "PLAYING"
        print(f"[{name}] Turn {index} | {status} | imposter={is_imposter}")

    try:
        raw_workflow_resp = await think_node(input_state)
    except Exception as e:
        print(f"[{name}] ERROR during LLM processing: {e}")
        # Return a safe decision — idle during play, skip vote during voting
        if is_voting:
            return {"vote": "skip", "chat": ""}
        return {"move_x": 0, "move_y": 0, "chat": "", "reason": "Error: " + str(e)[:50]}

    decision = raw_workflow_resp.get("decision", {})
    if is_voting:
        if "vote" in decision:
            print(f"[{name}] VOTED for: {decision['vote']}")
        else:
            print(f"[{name}] WARNING: voting schema but no 'vote' in LLM response — defaulting to skip")
            decision["vote"] = "skip"
    elif VERBOSE:
        print(f"[{name}] Action: move=({decision.get('move_x',0)},{decision.get('move_y',0)})"
              f" chat=\"{str(decision.get('chat',''))[:40]}\""
              f" attack={decision.get('attack','none')}")
    return decision

async def hard_node(game_data, index, personality):
    # print("This is a hardcoded node. It ignores the game state and always returns the same action.")
    hard_moves = [
        {"move_x": 0, "move_y": 0, "chat": "Stay", "reason": "Hardcode"},
        {"move_x": 1, "move_y": 0, "chat": "Right", "reason": "Hardcode"},
        {"move_x": -1, "move_y": 0, "chat": "Left", "reason": "Hardcode"},
        {"move_x": 0, "move_y": 1, "chat": "Up", "reason": "Hardcode"},
        {"move_x": 0, "move_y": -1, "chat": "Down", "reason": "Hardcode"},
        
    ]

    ascii_grid = game_data.get("world_view", "No map data provided.")

    print(f"ASCII Grid:\n{ascii_grid}"  )

    return hard_moves[index % len(hard_moves)]


# 2. WebSocket Communication
async def run_agent(personality, node):
    
    print("Connecting to Godot Server...")
    
    # try:
    async with websockets.connect(uri) as websocket:
        print("Successfully connected to Godot!")
        
        index = 0
        while True:
            # 1. Receive state
            message = await websocket.recv()
            game_data = json.loads(message)

            agent_name = game_data.get("name", "?")
            is_idle = game_data.get("is_idle", False)

            if VERBOSE:
                print(f"[{agent_name}] Raw game_data: {json.dumps(game_data, indent=2)[:500]}...")

            # If Idle then just ignore the update its just to keep the socket alive
            if is_idle:
                await websocket.send(json.dumps({}))
                continue

            if VERBOSE:
                print(game_data.get("bots", []))

            decision = await node(game_data, index, personality)

            # Echo phase_id so server can void stale responses
            if decision is not None and "phase_id" in game_data:
                decision["phase_id"] = game_data["phase_id"]

            # 3. Send back
            await websocket.send(json.dumps(decision))
            index += 1
            await asyncio.sleep(3)
                
    # except Exception as e:
    #     print(f"Connection lost: {e}")

async def main():
    # Load 3 random personalities from your folder
    persona_folder = "./personas" 
    personalities = load_random_personalities(persona_folder, count=5)

    # Create tasks for each personality loaded
    tasks = [run_agent(p, agent_node) for p in personalities]
    # hard_node can be used for testing without LLM calls

    print(f"🚀 Launching {len(tasks)} agents from folder...")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

