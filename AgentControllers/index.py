import asyncio
import json
import glob
import random
import os
import websockets
from dotenv import load_dotenv
from typing import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from openai import OpenAI

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

def render_ascii_grid(packet):
    # 1. Extract the world_view from the packet
    # The world_view is a 2D list: [rows][columns]
    grid_data = packet.get("world_view", [])
    
    if not grid_data:
        print("No world data found in packet.")
        return

    # 2. Define our character mapping
    # Adjust 'type' strings to match your Godot Atlas Coords or Custom Data
    mapping = {
        "walkable": ".",    # Ground
        "blocked": "#",     # Wall
        "player": "@",      # The bot itself
        "other_bot": "B"    # Other entities
    }

    # 3. Determine the center of the grid (where the player is)
    grid_height = len(grid_data)
    grid_width = len(grid_data[0]) if grid_height > 0 else 0
    center_y = grid_height // 2
    center_x = grid_width // 2

    print(f"\n--- Local Map View (Radius: {grid_height//2}) ---")
    
    ascii_rows = []
    for y in range(grid_height):
        line = ""
        for x in range(grid_width):
            tile = grid_data[y][x]
            
            # Logic to determine which character to print
            char = mapping["blocked"]
            
            if x == center_x and y == center_y:
                char = mapping["player"]
            elif tile.get("walkable"):
                char = mapping["walkable"]
            
            # Optional: Check if an 'other_bot' is on this specific tile
            # (Requires checking tile['x'] and tile['y'] against packet['bots'])
            
            line += char + " " # Space for better square-ish aspect ratio
        ascii_rows.append(line)

def get_action_model(first_time=False):
    # Base fields every action has
    fields = {
        "move_x": (int, Field(description="How many steps to move horizontally: -1 for left, 0 for idle, 1 for right.")),
        "move_y": (int, Field(description="How many steps to move vertically: -1 for up, 0 for idle, 1 for down.")),
        "chat": (str, Field(description="Chat message.")),
        "reason": (str, Field(description="Logic behind the move."))
    }
    
    # Dynamically add the 'name' field ONLY if it's the first time
    if first_time:
        fields["name"] = (str, Field(description="What is your name"))

    # Generate a new Pydantic class dynamically
    return create_model("DynamicAgentAction", **fields)

# 1. Define the AI's "Brain" State
class AgentState(TypedDict):
    game_data: dict
    decision: dict
    personality: str
    first_time: bool

uri = "ws://localhost:8080"


client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=os.getenv("OPENROUTER_API_KEY")
)

def create_chat_prompt_part(chat_logs):
    if not chat_logs:
        return "There are no recent chat messages."

    prompt_part = "Recent chat messages:\n"
    for log in chat_logs[-5:]:  # Include up to the last 5 messages
        prompt_part += f"- {log}\n"
    return prompt_part


async def think_node(state: AgentState):
    data = state['game_data']

    name_prompt = "Chose a name for other bots to see?" 
    if not state['first_time']:
        name_prompt = f"Your chosen name is {data['name']}."
    
    # Construct a prompt based on the specific agent's state
    prompt = (
        f"You are a bot. Wander Around and chat with other bots. "
        f"Here is your personality: {state['personality']}"
        f"{name_prompt}"
        f"Choose a movement: 'up', 'down', 'left', 'right', or 'idle'. "
        f"You can also respond to others or say something in chat. Provide your response in a structured format with 'move', 'chat', and 'reason' fields."
        f"You are a 2D grid explorer. Your surroundings are represented by an ASCII grid where:"
        f"@ is You (always the center)."
        f". is Walkable ground."
        f"# is a Wall or obstacle."
    )
    
    print("Invoking LLM with prompt:")
    print(prompt)
    print()

    game_data_promt = (

        f"Your current local map view is:\n"
        f"{render_ascii_grid(data)}\n"
        f"{create_chat_prompt_part(data.get('chat_logs', []))}"
    )

    # Game Context
    state["game_data"]["messages"] += {
        "role": "system",
        "content": prompt
    }

    DynamicAction = get_action_model(first_time=state["first_time"])
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": prompt
            },
            *state["game_data"].get("messages", [])[-10:],  # Include up to the last 5 messages in the conversation history
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

    # Use the unified LLM interface
    response = DynamicAction.model_validate_json(completion.choices[0].message.content)

    state["game_data"]["messages"].append({
        "role": "assistant",
        "content": response.model_dump_json()    })

    return {"decision": response}

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

                print(f"game_data: {game_data}")
                print()
                
                # 2. Call the full workflow, then extract the node output.
                # This preserves multi-node workflows while ensuring we only send
                # the agent action (move/chat/reason) back to the server.
                # Provide minimal AgentState to satisfy the typed signature
                input_state: AgentState = {
                    "game_data": game_data,
                    "decision": {},
                    "personality": personality,
                    "first_time": first_time,
                }

                raw_workflow_resp = await think_node(input_state)

                decision = raw_workflow_resp.get("decision", {})
                print(f"LLM Decision: {decision}")
                print()

                print(f"payload to send: {decision}")

                # 3. Send back
                await websocket.send(json.dumps(decision))
                await asyncio.sleep(3)

                first_time = False
                
    except Exception as e:
        print(f"Connection lost: {e}")

async def main():
    # Load 3 random personalities from your folder
    persona_folder = "./personas" 
    personalities = load_random_personalities(persona_folder, count=2)

    # Create tasks for each personality loaded
    tasks = [run_agent(p) for p in personalities]

    print(f"🚀 Launching {len(tasks)} agents from folder...")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

