#!/usr/bin/env bash
# SynapseCME end-to-end test against the live local stack.
# Ensures Neo4j/Postgres containers and the backend are running, then runs
# scripts/e2e.py. Exit non-zero on any failed check.
#
# Env overrides: API_PORT (default 8000), API_BASE, NEO4J_URI, NEO4J_USER,
# NEO4J_PASSWORD, POSTGRES_DSN
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
API_BASE="${API_BASE:-http://localhost:${API_PORT}}"
VENV_PY="$ROOT/backend/.venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "FAIL: backend venv not found at $VENV_PY (run 'uv sync' in backend/)" >&2
  exit 1
fi

step() { printf '\n== %s ==\n' "$1"; }

# --- 1. Neo4j + Postgres ------------------------------------------------------
step "Ensuring Neo4j + Postgres containers"
if ! docker ps --format '{{.Names}}' | grep -qx 'synapse-neo4j' || \
   ! docker ps --format '{{.Names}}' | grep -qx 'synapse-postgres'; then
  echo "Containers missing; starting them..."
  docker compose up -d neo4j postgres
fi
for i in $(seq 1 36); do
  n=$(docker inspect -f '{{.State.Health.Status}}' synapse-neo4j 2>/dev/null || echo missing)
  p=$(docker inspect -f '{{.State.Health.Status}}' synapse-postgres 2>/dev/null || echo missing)
  [ "$n" = "healthy" ] && [ "$p" = "healthy" ] && break
  sleep 5
  [ "$i" = "36" ] && { echo "FAIL: containers not healthy (neo4j=$n postgres=$p)" >&2; exit 1; }
done
echo "neo4j=healthy postgres=healthy"

# --- 2. Backend ----------------------------------------------------------------
step "Ensuring backend is running on :$API_PORT"
BACKEND_PID=""
if ! curl -sf "$API_BASE/api/health" >/dev/null 2>&1; then
  echo "Starting backend (uvicorn)..."
  (cd "$ROOT/backend" && "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT") &
  BACKEND_PID=$!
  trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT
  for i in $(seq 1 24); do
    curl -sf "$API_BASE/api/health" >/dev/null 2>&1 && break
    sleep 2
    [ "$i" = "24" ] && { echo "FAIL: backend did not become healthy" >&2; exit 1; }
  done
fi
echo "backend up at $API_BASE"

# --- 3. E2E checks ---------------------------------------------------------------
step "Running E2E checks"
export API_BASE
"$VENV_PY" "$ROOT/scripts/e2e.py"
