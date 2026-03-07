import asyncio
import json
import os
import websockets
from dotenv import load_dotenv
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver # This is the "brain" storage
from pydantic import BaseModel, Field
from google.genai import errors

from google.genai import types

# Load variables from .env
load_dotenv()

safety_settings={
    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_ONLY_HIGH",
    "HARM_CATEGORY_HARASSMENT": "BLOCK_LOW_AND_ABOVE",
}

class AgentAction(BaseModel):
    move: str = Field(description="The direction to move: 'up', 'down', 'left', 'right', or 'idle'.")
    chat: str = Field(description="A chat message to be sent to surrounding bots")
    reason: str = Field(description="A brief explanation of why this action was chosen.")

# 1. Define the AI's "Brain" State
class AgentState(TypedDict):
    game_data: dict
    decision: str

# Initialize Gemini (Flash is recommended for fast game response times)
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.2, # Lower temperature = more consistent game commands,
    # safety_settings=safety_settings,
)

structured_llm = llm.with_structured_output(AgentAction)

def think_node(state: AgentState):
    data = state['game_data']
    
    # Construct a prompt based on the specific agent's state
    prompt = (
        f"You are a bot. Your current position is {data['pos']} Wander Around and chat with other bots. "
        f"Your ID is {data['id']}. "
        "Choose a movement: 'up', 'down', 'left', 'right', or 'idle'. "
        "Respond to others or say something in chat"
    )
    
    print("Invoking")
    response = {
        "move": "idle",
        "reason": "it errored idk"
    }
    try:
        response = structured_llm.invoke(prompt)
    except errors.ClientError as e:
        # ClientErrors cover 400 (Bad Request), 403 (Forbidden), and 429 (Rate Limit)
        if e.code == 429:
            print("⚠️ 429: Rate limit hit! Slowing down...")
        elif e.code == 400:
            print("❌ 400: Potential Safety Block or malformed request.")
        else:
            print(f"🚫 Client Error {e.code}: {e.message}")
        # return {"decision": "idle", "reason": "API_CLIENT_ERROR"}

    except errors.ServerError as e:
        # ServerErrors cover 500 (Internal Error), 503 (Unavailable), etc.
        print(f"☁️ Google Server Error {e.code}: Try again in a moment.")
        # return {"decision": "idle", "reason": "GOOGLE_SERVER_DOWN"}

    except Exception as e:
        print(f"🔥 Unknown Error: {e}")
        # return {"decision": "idle", "reason": "CRASH"}
    
    # Clean the response to ensure it's just the command
    print(f"Response{response}")
    return {"move": response.move, "chat": response.chat}

# Build the LangGraph
workflow = StateGraph(AgentState)
workflow.add_node("think", think_node)
workflow.add_edge(START, "think")
workflow.add_edge("think", END)
app = workflow.compile()

# 2. WebSocket Communication
async def run_agent():
    uri = "ws://localhost:8080"
    print("Connecting to Godot Server...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Successfully connected to Godot!")
            
            while True:
               # 1. Receive state
                message = await websocket.recv()
                game_data = json.loads(message)

                print(f"game_data: {game_data}")
                print()
                
                # 2. IMPORTANT: Use ainvoke (async invoke)
                # This prevents the "stuck" behavior
                response = await app.ainvoke({"game_data": game_data})
                print(response)
                
                # 3. Send back
                await websocket.send(json.dumps(response))
                await asyncio.sleep(3)
                
    except Exception as e:
        print(f"Connection lost: {e}")


if __name__ == "__main__":
    asyncio.run(run_agent())