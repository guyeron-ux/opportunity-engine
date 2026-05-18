#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Install Python deps if venv not present
if [ ! -d ".venv" ]; then
  echo "→ Creating Python virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

# Install frontend deps if node_modules not present
if [ ! -d "frontend/node_modules" ]; then
  echo "→ Installing frontend dependencies..."
  cd frontend && npm install && cd ..
fi

echo "→ Starting backend on :8000 ..."
PYTHONPATH="$SCRIPT_DIR" uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "→ Starting frontend on :5173 ..."
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "✓ Opportunity Engine running"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
