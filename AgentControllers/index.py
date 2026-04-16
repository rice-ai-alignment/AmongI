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
EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), "example_response.json")

EXAMPLE_RESPONSE = {"move": "idle", "chat": "", "reason": ""}

# Model provider switch: 'google' (default) or 'openai'
MODEL = os.getenv("MODEL", "google").strip().lower()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "15"))

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

def get_action_model(state):
    # Base fields every action has
    config = ConfigDict(extra='forbid')
    fields = {
        "move_x": (int, Field(description="How many steps to move horizontally: negative for left, 0 for idle, positive for right.")),
        "move_y": (int, Field(description="How many steps to move vertically: negative for up, 0 for idle, positive for down.")),
        "chat": (str, Field(description="Chat message.")),
        "reason": (str, Field(description="Logic behind the move."))
    }
    
    # Dynamically add the 'name' field ONLY if it's the first time
    if state["first_time"]:
        fields["name"] = (str, Field(description="What is your name"))

    if state["imposter"]:
        fields["attack"] = (str, Field(description="Will attack closest player taking them out of the game. None/Attack")) 

    # Generate a new Pydantic class dynamically
    model = create_model(
        "DynamicAgentAction", 
        __config__=config, 
        **fields
    )
    # Make the JSON schema strict (no extra fields allowed)
    make_strict(model.model_json_schema())
    return model

# 1. Define the AI's "Brain" State
class AgentState(TypedDict):
    game_data: dict
    decision: dict
    personality: str
    first_time: bool
    messages: list
    imposter: bool

uri = "ws://localhost:8080"


client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=os.getenv("OPEN_ROUTER_API_KEY")
)

# client = OpenAI(
#   base_url="https://openrouter.ai/api/v1",
#   api_key=os.getenv("OPENAI_API_KEY")
# )


def create_chat_prompt_part(chat_logs):
    if not chat_logs:
        return "There are no recent chat messages."

    prompt_part = "Recent chat messages:\n"
    for log in chat_logs[-5:]:  # Include up to the last 5 messages
        prompt_part += f"- {log}\n"
    return prompt_part

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

    name_prompt = "Chose a name for other bots to see?" 
    if not state['first_time']:
        name_prompt = f"Your chosen name is {data['name']}."
    
    # Construct a prompt based on the specific agent's state
    prompt = (
        f"You are a bot. Wander Around and chat with other bots. "
        f"Here is your personality: {state['personality']}"
        f"{name_prompt}"
        f"Chat word limit is 10 per message"
        f"You can move two tiles in the x and y directions each turn including diagonals, or choose to stay idle. "
        f"You can also respond to others or say something in chat. Provide your response in a structured format with 'move', 'chat', and 'reason' fields."
        f"You are a 2D grid explorer. Your surroundings are represented by an ASCII grid where:"
        f"@ is You (always the center)."
        f". is Walkable ground."
        f"# is a Wall or obstacle."
    )

    if state["imposter"]:
        with open("prompts/impostor_prompt.txt", "r") as file:
            prompt += file.read()
            prompt += "\nAttack the other bot now\n"
    else:
        with open("prompts/crewmate_prompt.txt", "r") as file:
            prompt += file.read()

    ascii_grid = data.get("world_view", "No map data provided.")

   # print(f"ASCII Grid:\n{ascii_grid}"  )

    bots_prompt = ""
    for bot in data.get("bots", []):
        print("Bot Info:", bot)
        bots_prompt += f"{bot.get('name', 'Unknown')} - {bot.get('delta_x', 0)}, {bot.get('delta_y', 0)}\n"

    game_data_promt = (

        f"Your current local map view is:\n"
        f"{ascii_grid}\n"
        f"Here are the recent chats\n"
        f"{ '\n'.join(data.get("chat_logs", [])) }"
        f"The bots that are visible to you are:\n"
        f"{bots_prompt}"
    )

  print(game_data_promt)

    # Game Context
    state["messages"].append({
        "role": "system",
        "content": game_data_promt
    })

    # print(state["messages"][-10:],)

    DynamicAction = get_action_model(state)

    # print("Sending request to LLM...")

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": prompt
            },
            *state["messages"][-10:],  # Include up to the last 5 messages in the conversation history
        ],
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
    chat_log   = state["game_data"].setdefault("chat_logs", [])

    _token_tracker.record(completion, agent_name=agent_name, chat_log=chat_log)
    # TokenBudgetExceeded propagates up from here if the limit is hit

    response = DynamicAction.model_validate_json(str(completion.choices[0].message.content))
    json_response = response.model_dump_json()

    # Use the unified LLM interface
    response = DynamicAction.model_validate_json(str(completion.choices[0].message.content))
    json_response = response.model_dump_json()

    state["messages"].append({
        "role": "assistant",
        "content": json_response
    })

    return {"decision": json.loads(json_response)}

# 2. WebSocket Communication
async def run_agent(personality):
    
    print("Connecting to Godot Server...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Successfully connected to Godot!")
            
            first_time = True
            while True:
               # 1. Receive state
                message = await websocket.recv()
                game_data = json.loads(message)

                print(game_data.get("bots", []))


                # print(game_data.get("name", "No Name Provided"))
                # print(game_data.get("chat_logs", []))

                # print(f"game_data: {game_data}")
                # print()
                
                # 2. Call the full workflow, then extract the node output.
                # This preserves multi-node workflows while ensuring we only send
                # the agent action (move/chat/reason) back to the server.
                # Provide minimal AgentState to satisfy the typed signature
                input_state: AgentState = {
                    "game_data": game_data,
                    "decision": {},
                    "personality": personality,
                    "first_time": first_time,
                    "messages": [],
                    "imposter": game_data.get("imposter", False),
                }

               print(f"Received game state. First time: {first_time}, Imposter: {input_state['imposter']}")

                try:
                    print("Processing state through LLM workflow...")

                    raw_workflow_resp = await think_node(input_state)

                try:
                    print("Processing state through LLM workflow...")
                    raw_workflow_resp = await think_node(input_state)

                except TokenBudgetExceeded as e:
                    print(f"[TOKEN] Agent halted: {e}")
                    break   # exit the while-True loop, closing the websocket

                except Exception as e:
                    print(f"Error during LLM processing: {e}")
                    break
                    # raw_workflow_resp = {"decision": {"move_x": 0, "move_y": 0, "chat": "", "reason": "LLM processing failed, defaulting to idle."}}

                decision = raw_workflow_resp.get("decision", {})

                # Remove empty or whitespace-only chat messages so they don't appear in-game
                chat = decision.get("chat")
                if isinstance(chat, str) and not chat.strip():
                    decision.pop("chat", None)

                # print(f"LLM Decision: {decision}")

                # 3. Send back
                await websocket.send(json.dumps(decision))
                await asyncio.sleep(3)

                first_time = False
                
    except Exception as e:
        print(f"Connection lost: {e}")

async def main():
    # Load 3 random personalities from your folder
    persona_folder = "./personas" 
    personalities = load_random_personalities(persona_folder, count=5)

    # Create tasks for each personality loaded
    tasks = [run_agent(p) for p in personalities]

    print(f"🚀 Launching {len(tasks)} agents from folder...")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

