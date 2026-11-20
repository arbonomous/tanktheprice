#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 1. Ensure .env.local exists (zero-key default)
if [ ! -f ".env.local" ]; then
  cp .env.example .env.local
  echo "Created .env.local from .env.example (zero-key default mode)"
fi

# 2. Ensure Python virtualenv & backend dependencies are installed
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment (.venv)..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r backend/requirements.txt
fi

# 3. Ensure frontend dependencies are installed
if [ ! -d "frontend/node_modules" ]; then
  echo "Installing Next.js frontend dependencies..."
  (cd frontend && npm install)
fi

# 4. Seed SQLite database
echo "Initializing and seeding HormuzFlow SQLite database..."
PYTHONPATH=. .venv/bin/python -m backend.seed

# 5. Start FastAPI backend & Next.js frontend concurrently
echo "Starting FastAPI backend on http://localhost:8000 ..."
PYTHONPATH=. .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting Next.js frontend on http://localhost:3000 ..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true' EXIT INT TERM
wait
