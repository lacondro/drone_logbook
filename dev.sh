#!/usr/bin/env bash
# Dev launcher (bash / macOS / Linux / Git-Bash): backend on :8137, frontend on :5173.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# venv detection works for both Windows (Scripts) and POSIX (bin) layouts.
if [ -f "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/backend/.venv/Scripts/python.exe"
else
  PY="$ROOT/backend/.venv/bin/python"
fi

if [ ! -x "$PY" ] && [ ! -f "$PY" ]; then
  echo "Creating backend venv..."
  python3 -m venv "$ROOT/backend/.venv"
  if [ -f "$ROOT/backend/.venv/Scripts/python.exe" ]; then PY="$ROOT/backend/.venv/Scripts/python.exe"; else PY="$ROOT/backend/.venv/bin/python"; fi
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install -r "$ROOT/backend/requirements.txt"
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend deps..."
  (cd "$ROOT/frontend" && npm install)
fi

echo "Backend  -> http://127.0.0.1:8137"
echo "Frontend -> http://localhost:5173  (open this)"
trap 'kill 0' EXIT
(cd "$ROOT/backend" && "$PY" -m uvicorn main:app --reload --port 8137) &
(cd "$ROOT/frontend" && npm run dev) &
wait
