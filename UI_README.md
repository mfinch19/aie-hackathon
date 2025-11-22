# Security Agent Dashboard

React + FastAPI dashboard for the Security Agent.

## Setup

### Backend (FastAPI)

1. Install Python dependencies:
```bash
pip install fastapi uvicorn websockets
```

2. Run the server:
```bash
python server.py
```

The API will be available at `http://localhost:8000`

### Frontend (React)

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Run the dev server:
```bash
npm run dev
```

The UI will be available at `http://localhost:5173`

## Usage

1. Start the FastAPI backend (`python server.py`)
2. Start the React frontend (`cd frontend && npm run dev`)
3. Open `http://localhost:5173` in your browser
4. Click the phase buttons to run:
   - **Reconnaissance**: Runs `qa_agent.py` to explore and fuzz the target
   - **Planning**: Runs `exploit_planner.py` to generate exploits
   - **Attack**: Runs `attack.py` to execute the exploits

## Features

- **Live Logs**: Real-time terminal output via WebSocket
- **Stats Dashboard**: Track vulnerabilities, exploits, and success rate
- **Results Visualization**: View found vulnerabilities and attack evidence
- **Phase Control**: Trigger each stage of the attack pipeline
