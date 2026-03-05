import asyncio
import json
import websockets
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

# 1. Define the AI's "Brain" State
class AgentState(TypedDict):
    game_data: dict
    decision: str

llm = ChatOpenAI(model="gpt-4o-mini")

def think_node(state: AgentState):
    # Pass game state to ChatGPT
    prompt = f"The player is at {state['game_data']['player_pos']}. Command: 'left' or 'right'?"
    response = llm.invoke(prompt)
    return {"decision": response.content.lower()}

# Build the Graph
workflow = StateGraph(AgentState)
workflow.add_node("think", think_node)
workflow.add_edge(START, "think")
workflow.add_edge("think", END)
app = workflow.compile()

# 2. WebSocket Communication
async def run_agent():
    uri = "ws://localhost:8080"
    async with websockets.connect(uri) as websocket:
        print("Connected to Godot!")
        
        while True:
            # Receive state from Godot
            message = await websocket.recv()
            game_data = json.loads(message)
            
            # Run LangGraph to get a decision
            result = app.invoke({"game_data": game_data})
            command = result["decision"]
            
            # Send command back to Godot
            await websocket.send(json.dumps({"move": command}))
            await asyncio.sleep(0.5) # Don't overwhelm the LLM

if __name__ == "__main__":
    asyncio.run(run_agent())