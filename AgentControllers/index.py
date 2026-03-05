import asyncio
import json
import os
import websockets
from dotenv import load_dotenv
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI

# Load variables from .env
load_dotenv()

# 1. Define the AI's "Brain" State
class AgentState(TypedDict):
    game_data: dict
    decision: str

# Initialize Gemini (Flash is recommended for fast game response times)
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.2 # Lower temperature = more consistent game commands
)

def think_node(state: AgentState):
    data = state['game_data']
    
    # Construct a prompt based on the specific agent's state
    prompt = (
        f"You are a Minecraft bot. Your current position is {data['pos']} Go Left. "
        f"Your ID is {data['id']}. "
        "Choose a movement: 'up', 'down', 'left', 'right', or 'idle'. "
        "Respond with ONLY the word."
    )
    
    response = llm.invoke(prompt)
    # Clean the response to ensure it's just the command
    command = response.content.strip().lower()
    return {"decision": command}

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
                # Receive state from Godot
                message = await websocket.recv()
                game_data = json.loads(message)
                
                # Run LangGraph decision loop
                result = app.invoke({"game_data": game_data})
                command = result["decision"]
                
                # Send the decision back
                await websocket.send(json.dumps({"move": command}))
                print(f"Agent {game_data['id']} sent command: {command}")
                
                # Small delay to prevent API rate limiting
                await asyncio.sleep(0.1) 
                
    except Exception as e:
        print(f"Connection lost: {e}")

if __name__ == "__main__":
    asyncio.run(run_agent())