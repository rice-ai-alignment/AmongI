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

import openai
from pydantic import create_model, Field
# Load variables from .env
load_dotenv()

# Load example response for shaping prompts and coercion
EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), "example_response.json")
try:
    with open(EXAMPLE_PATH, "r", encoding="utf-8") as _f:
        EXAMPLE_RESPONSE = json.load(_f)
except Exception:
    EXAMPLE_RESPONSE = {"move": "idle", "chat": "", "reason": ""}

# Model provider switch: 'google' (default) or 'openai'
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "google").strip().lower()
# OpenAI settings (used only when MODEL_PROVIDER=openai)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# Timeout (seconds) for external LLM calls to avoid hanging forever
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "15"))

safety_settings={
    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_ONLY_HIGH",
    "HARM_CATEGORY_HARASSMENT": "BLOCK_LOW_AND_ABOVE",
}

def load_random_personalities(folder_path: str, count: int):
    # 1. Find all .txt files in the folder
    search_pattern = os.path.join(folder_path, "*.txt")
    all_files = glob.glob(search_pattern)
    
    if not all_files:
        print(f"⚠️ No personality files found in {folder_path}!")
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


def get_action_model(first_time=False):
    # Base fields every action has
    fields = {
        "move": (str, Field(description="The direction to move: 'up', 'down', 'left', 'right', or 'idle'.")),
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


if MODEL_PROVIDER == "openai":
    client = openai.OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://openrouter.ai/api/v1",
) 

elif MODEL_PROVIDER == "google":
    # Initialize Gemini (Flash is recommended for fast game response times)
    gemini_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.2, # Lower temperature = more consistent game commands,
        # safety_settings=safety_settings,
)
    gemini_structured_llm_first = gemini_llm.with_structured_output(get_action_model(True))
    gemini_structured_llm = gemini_llm.with_structured_output(get_action_model(False))


async def _call_google(prompt: str, first_time=False):
    """Call the Google structured LLM (sync or async) and return its raw response.

    Returns whatever the structured LLM returns (could be an object with attributes
    or a dict). Exceptions are propagated to the caller.
    """
    print("[LLM] calling Google provider...")
    if first_time:
        return await gemini_structured_llm_first.ainvoke(prompt)
    else:
        return await gemini_structured_llm.ainvoke(prompt)
        #     return await loop.run_in_executor(None, gemini_structured_llm.invoke, prompt)

async def _call_openai(prompt: str, first_time):
    """Call OpenAI (sync client wrapped in executor) and return the assistant text.

    This function normalizes the various OpenAI response shapes into a single
    string (or None). It will raise if the openai package is not available.
    """
    if openai is None:
        raise RuntimeError("openai package is not installed")

    messages = [{"role": "user", "content": prompt}]
    loop = asyncio.get_running_loop()

    def _sync_call_new_client():
        # new-style chat completions
        return client.chat.completions.parse(
            model=OPENAI_MODEL, 
            messages=messages, 
            temperature=0.2, 
            response_format=get_action_model(first_time)
            )

    print("[LLM] calling OpenAI provider (new interface)...")
    resp = await loop.run_in_executor(None, _sync_call_new_client)

    # print(f"[LLM] OpenAI response: {resp}")

    if not resp:
        return None

    if not hasattr(resp.choices[0].message, "parsed"):
        print("⚠️ OpenAI response missing 'parsed' content, cannot extract command.")
        return None
    
    command = resp.choices[0].message.parsed.model_dump()

    return command


async def fetch_llm(prompt: str, first_time=False):
    """Unified entrypoint to call the configured LLM provider.

    Returns provider-specific response (object, dict, or string). Any errors are
    caught and logged; function returns None on failure.
    """
    try:
        print(f"[LLM] provider={MODEL_PROVIDER}, timeout={LLM_TIMEOUT}s")
        if MODEL_PROVIDER == "openai":
            return await asyncio.wait_for(_call_openai(prompt, first_time), timeout=LLM_TIMEOUT)
        else:
            return await asyncio.wait_for(_call_google(prompt, first_time), timeout=LLM_TIMEOUT)
    except asyncio.TimeoutError:
        print(f"⚠️ LLM call timed out after {LLM_TIMEOUT}s (provider={MODEL_PROVIDER})")
        return None
    except Exception as e:
        # Keep logs concise but informative for debugging
        print(f"⚠️ LLM call failed (provider={MODEL_PROVIDER}): {e}")
        return None

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
        f"Chat Logs:"
        f"{create_chat_prompt_part(data.get('chat_logs', []))}"
        f"Choose a movement: 'up', 'down', 'left', 'right', or 'idle'. "
        f"You can also respond to others or say something in chat. Provide your response in a structured format with 'move', 'chat', and 'reason' fields."
    )
    
    print("Invoking LLM with prompt:")
    print(prompt)
    print()
    # Use the unified LLM interface
    response = await fetch_llm(prompt, first_time=state['first_time'])

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
                    "first_time": first_time
                }

                raw_workflow_resp = await think_node(input_state)

                decision = raw_workflow_resp.get("decision", {})
                print(f"LLM Decision: {decision}")
                print()

                # print(f"payload to send: {payload}")

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