# Among-I

A multi-agent LLM simulation built in Godot 4. AI agents with distinct personalities explore a 2D world, move around, and chat with each other in real time. Each agent is powered by a large language model (Google Gemini or OpenAI) and makes autonomous decisions about where to go and what to say.

## What it looks like

Colorful Among Us-style sprites wander a 2D scene. A chat log panel in the bottom-left corner shows what the agents are saying to each other. Each agent's name and latest message float above their sprite.

## Architecture

```
┌─────────────────────┐        WebSocket         ┌──────────────────────────┐
│   Godot 4 (Game)    │ ◄──────────────────────► │   Python Agent Runner    │
│                     │   port 8080              │                          │
│  - Renders world    │                          │  - Loads LLM personas    │
│  - Moves sprites    │  Game state (JSON) ──►   │  - Calls Gemini/OpenAI   │
│  - Shows chat HUD   │  ◄── Actions (JSON)      │  - Sends move + chat     │
└─────────────────────┘                          └──────────┬───────────────┘
                                                            │
                                                    ┌───────▼────────┐
                                                    │  LLM API       │
                                                    │  (Gemini/GPT)  │
                                                    └────────────────┘
```

**Communication format (every ~3 seconds):**

Godot → Python (game state):
```json
{
  "id": 12345,
  "pos": { "x": 200, "y": 150 },
  "bots": [{ "distance": 120.5, "angle": 0.78 }],
  "name": "CowboyJack",
  "chat_logs": ["Nona: existence is a rumor.", "CowboyJack: Yeehaw!"]
}
```

Python → Godot (agent decision):
```json
{
  "name": "CowboyJack",
  "move": "right",
  "chat": "Howdy partner, mighty fine day ain't it?",
  "reason": "Another agent is nearby, going to say hello"
}
```

## Prerequisites

| Requirement | Version |
|---|---|
| [Godot Engine](https://godotengine.org/download/) | 4.x |
| Python | 3.10+ |
| Google Gemini API key | (default) |
| OpenAI API key | (optional, instead of Gemini) |

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/rice-ai-alignment/among-i.git
cd among-i
```

### 2. Install Python dependencies

```bash
cd AgentControllers
pip install langgraph langchain-google-genai websockets python-dotenv pydantic google-genai openai
```

### 3. Set up your API key

Create a file called `.env` inside the `AgentControllers/` folder:

```bash
# AgentControllers/.env

# Use Google Gemini (default):
GOOGLE_API_KEY=your_google_api_key_here

# Or use OpenAI instead:
# MODEL_PROVIDER=openai
# OPENAI_API_KEY=your_openai_api_key_here
# OPENAI_MODEL=gpt-4o-mini
```

Get a free Google Gemini API key at [aistudio.google.com](https://aistudio.google.com).

### 4. Import the Godot project

1. Open Godot 4
2. In the Project Manager, click **Import**
3. Navigate to the `among-i/` subfolder and select `project.godot`
4. Click **Import & Edit**

## Running the Simulation

You need two things running at once: the Godot game (the server) and the Python agents (the clients).

**Step 1 — Start the Godot server:**
- In the Godot editor, press **F5** (or click the ▶ Play button in the top-right)
- The game window opens and waits for agents to connect

**Step 2 — Start the Python agents (in a separate terminal):**
```bash
cd AgentControllers
python index.py
```

Two agents with randomly selected personalities will connect, spawn as sprites, and start moving and chatting. Watch the chat log panel in the bottom-left corner of the game window.

**To stop:** Close the Godot window, then press `Ctrl+C` in the terminal.

## Project Structure

```
among-i/                    # Godot project root
├── project.godot           # Godot project config (entry point)
├── FirstScene.tscn         # Main scene: loads server + chat HUD
├── Server.gd               # WebSocket server, manages all agents
├── Player.tscn             # Agent sprite template (body + name + chat bubble)
├── player.gd               # Agent movement logic
├── ChatBox.tscn            # Chat log HUD panel (bottom-left overlay)
├── ChatBox.gd              # Chat log logic (add messages, auto-scroll)
└── AmongUsSprites.jpg      # Spritesheet for agent visuals

AgentControllers/           # Python backend
├── index.py                # Main agent driver (LangGraph + LLM)
├── agent_test.py           # Quick API key test
├── example_response.json   # Template for LLM structured output
└── personas/               # Personality files for each agent
    ├── CowboyJack.txt
    ├── Nona_the_Nihilist.txt
    ├── Biscuit.txt
    └── ...                 # 12+ personas included
```

## Persona System

Each agent is given a personality from a text file in `AgentControllers/personas/`. Two personas are randomly selected each run.

To create a new persona:
1. Create a `.txt` file in `AgentControllers/personas/`
2. Write a character description in natural language — describe their personality, speaking style, quirks, and worldview
3. The file is loaded as a system prompt for the LLM, shaping how that agent speaks and behaves

Example excerpt from `CowboyJack.txt`:
> You are CowboyJack, a rugged cowboy who communicates using Western slang and frontier wisdom...

## Key Settings

In `Server.gd`:
- `UPDATE_INTERVAL = 3.0` — how often (in seconds) the server sends state to each agent
- `CHAT_DISTANCE = 10000` — how close two agents must be to hear each other's messages

In `AgentControllers/index.py`:
- `LLM_TIMEOUT = 15` — seconds before an LLM call times out
- `MODEL_PROVIDER` — set to `"google"` or `"openai"` in `.env`

This project is maintained by [Rice AI Alignment](https://github.com/rice-ai-alignment). MIT License.
