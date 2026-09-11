#!/usr/bin/env bash
# SynapseCME local runner (native macOS development without Docker).
#
# Runs:
#   1. QVAC inference server natively on macOS with Apple Silicon Metal GPU (port 11434)
#   2. FastAPI backend (port 8000)
#   3. Nuxt frontend (port 3001)
#   4. Caddy gateway (port 3000, proxies frontend + backend)
#
# Gracefully terminates all services on Ctrl+C.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}=====================================================${NC}"
echo -e "${CYAN}  SynapseCME — Local Native macOS Runner (No Docker) ${NC}"
echo -e "${CYAN}=====================================================${NC}"

# PIDs to kill on exit
PIDS=()

cleanup() {
    echo ""
    echo -e "${YELLOW}>> Stopping all local services...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo -e "${GREEN}>> All services stopped.${NC}"
}
trap cleanup SIGINT SIGTERM EXIT

# 1) Check QVAC inference server ----------------------------------------------
if command -v qvac >/dev/null 2>&1 || [ -f "/opt/homebrew/bin/qvac" ]; then
    echo -e "${GREEN}>> Starting native QVAC server (Apple Silicon Metal GPU) on :11434...${NC}"
    "$REPO_ROOT/scripts/qvac-mac-host-serve.sh" &
    PIDS+=($!)
else
    echo -e "${YELLOW}>> 'qvac' CLI not installed yet. Skipping local inference server.${NC}"
    echo -e "${YELLOW}   (Run 'bun install -g @qvac/cli' or 'npm install -g @qvac/cli' to enable Metal GPU inference.)${NC}"
fi

# 2) Check database connectivity (informational) ------------------------------
if ! nc -z 127.0.0.1 5432 2>/dev/null; then
    echo -e "${YELLOW}>> PostgreSQL (port 5432) is not running.${NC}"
    echo -e "${YELLOW}   Backend will start in graceful mode (fallback for tests/demos).${NC}"
    echo -e "${YELLOW}   To enable full persistence: brew services start postgresql@16${NC}"
fi

if ! nc -z 127.0.0.1 7687 2>/dev/null; then
    echo -e "${YELLOW}>> Neo4j (port 7687) is not running.${NC}"
    echo -e "${YELLOW}   Backend will start in graceful mode without graph database.${NC}"
    echo -e "${YELLOW}   To enable full GraphRAG: brew services start neo4j${NC}"
fi

# 3) Start FastAPI backend ----------------------------------------------------
echo -e "${GREEN}>> Starting FastAPI backend on http://127.0.0.1:8000...${NC}"
(
    cd "$REPO_ROOT/backend"
    export RAG_DIR="${REPO_ROOT}/volumes/rag"
    export POSTGRES_DSN="${POSTGRES_DSN:-postgresql://synapse:synapse-local-dev@127.0.0.1:5432/synapse_state}"
    export NEO4J_URI="${NEO4J_URI:-bolt://127.0.0.1:7687}"
    export QVAC_BASE_URL="${QVAC_BASE_URL:-http://127.0.0.1:11434}"
    mkdir -p "$RAG_DIR"
    exec uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
) &
PIDS+=($!)

# 4) Start Nuxt frontend ------------------------------------------------------
echo -e "${GREEN}>> Starting Nuxt frontend on http://127.0.0.1:3001...${NC}"
(
    cd "$REPO_ROOT/frontend"
    export PORT=3001
    exec bun run dev -- --port 3001
) &
PIDS+=($!)

# 5) Start Caddy Gateway if available -----------------------------------------
if command -v caddy >/dev/null 2>&1; then
    echo -e "${GREEN}>> Starting Caddy Gateway on http://localhost:3000...${NC}"
    (
        cd "$REPO_ROOT"
        exec caddy run --config gateway/Caddyfile.local
    ) &
    PIDS+=($!)
else
    echo -e "${YELLOW}>> Caddy is not installed. Access frontend directly at http://localhost:3001${NC}"
    echo -e "${YELLOW}   (Run 'brew install caddy' to enable unified port 3000 gateway.)${NC}"
fi

echo ""
echo -e "${CYAN}=====================================================${NC}"
echo -e "${GREEN}  SynapseCME is running!${NC}"
echo -e "  - Public Gateway: ${CYAN}http://localhost:3000${NC} (if Caddy installed)"
echo -e "  - Frontend direct: ${CYAN}http://localhost:3001${NC}"
echo -e "  - Backend API:    ${CYAN}http://localhost:8000/api/health${NC}"
echo -e "  - QVAC Metal GPU: ${CYAN}http://localhost:11434/v1/models${NC}"
echo -e "${CYAN}=====================================================${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services.${NC}"
echo ""

# Wait for all background jobs
wait
