# Opportunity Discovery Engine

A full-stack automated startup opportunity discovery system. A multi-agent pipeline monitors live sources (business news, developer communities, long-form analysis), extracts pain point signals, runs deep research, scores opportunities with a composite rubric, and presents them in a real-time filterable dashboard.

## Architecture

```
Scouts (3 parallel) → Analyst → Rating Agent → Database → FastAPI → React UI
                                                        ↕
                                               WebSocket (live updates)
```

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required variables:
| Variable | Description |
|---|---|
| `LLM_API_KEY` | Minimax (or any OpenAI-compatible) API key |
| `LLM_BASE_URL` | API base URL (default: `https://api.minimax.chat/v1`) |
| `LLM_MODEL` | Model name (default: `MiniMax-M2.7`) |
| `TAVILY_API_KEY` | Tavily search API key ([get one free](https://tavily.com)) |

### 2. Run

```bash
chmod +x run.sh
./run.sh
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### 3. Trigger a discovery cycle

Via UI: click the **▶ Run Cycle** button.

Via API:
```bash
curl -X POST http://localhost:8000/api/cycle/run
```

Watch the live updates in the notification bell as scouts find signals, the analyst researches them, and new opportunities appear in the table.

## Manual Setup (without run.sh)

**Backend:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn backend.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Scoring Rubric

| Factor | Weight | 90-100 | 70-89 | 50-69 |
|---|---|---|---|---|
| Market Size | 25% | $10B+ TAM | $1-10B | $100M-1B |
| Pain Severity | 25% | Critical ops pain | Significant friction | Moderate |
| Solution Clarity | 15% | Clear MVP path | Good direction | Concept only |
| Competitive Insight | 15% | Fragmented market | Incumbent gaps | Competitive |
| Monetization | 15% | Proven models | Clear path | Possible |
| Signal Authority | 5% | VCs + major press | Mixed signals | Community only |

Composite: `MS×0.25 + PS×0.25 + SC×0.15 + CI×0.15 + MP×0.15 + SA×0.05`

- **Moonshot**: composite ≥ 80, high risk/high reward
- **Pragmatic**: composite 60-79, incremental innovation

## API Reference

```
GET  /api/opportunities          List opportunities (filterable)
GET  /api/opportunities/{id}     Single opportunity detail
POST /api/opportunities/{id}/annotate       Add notes
POST /api/opportunities/{id}/archive        Archive
POST /api/opportunities/{id}/request-info  Queue deep research
GET  /api/settings               Get user settings
PATCH /api/settings              Update threshold/prefs
POST /api/cycle/run              Manually trigger cycle
GET  /api/cycle/status           Cycle running status
WS   /ws                         Real-time updates stream
```

## Scheduler

Cycles run automatically:
- **Daily 06:00 UTC**: full discovery scan
- **Sunday 14:00 UTC**: weekly deep dive

## Project Structure

```
backend/
  agents/          AI agents (scout × 3, analyst, rating, orchestrator)
  models/          Pydantic models + JSON database
  api/             FastAPI routes + WebSocket manager
  config.py        Settings (reads from .env)
  main.py          App entry point + scheduler startup
frontend/
  src/
    components/    React UI components
    hooks/         useWebSocket hook
    api.ts         API client
data/              JSON database files
logs/              Per-agent log files
backups/           Daily DB backups
```
