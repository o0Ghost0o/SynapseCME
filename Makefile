# SynapseCME Makefile — Native macOS local execution without Docker.
#
# Runs the full platform natively on Apple Silicon with Metal GPU acceleration:
#   - QVAC inference server (Apple M2 Metal GPU, port 11434)
#   - FastAPI backend (port 8000)
#   - Nuxt frontend (port 3001)
#   - Caddy gateway (port 3000)

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Colors
CYAN   := \033[0;36m
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m

.PHONY: help setup install-deps setup-db qvac backend frontend gateway dev test seed stop clean

help: ## Show this help message
	@echo ""
	@echo -e "${CYAN}SynapseCME — Local Native macOS Commands${NC}"
	@echo "=========================================="
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  ${GREEN}%-15s${NC} %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""

install-deps: ## Install required macOS CLI tools (bun, uv, caddy, qvac CLI)
	@echo -e "${GREEN}>> Checking & installing Homebrew dependencies...${NC}"
	@command -v bun >/dev/null 2>&1 || HOMEBREW_NO_AUTO_UPDATE=1 brew install bun
	@command -v uv >/dev/null 2>&1 || HOMEBREW_NO_AUTO_UPDATE=1 brew install uv
	@command -v caddy >/dev/null 2>&1 || HOMEBREW_NO_AUTO_UPDATE=1 brew install caddy
	@if ! command -v qvac >/dev/null 2>&1; then \
		echo -e "${GREEN}>> Installing @qvac/cli globally...${NC}"; \
		bun install -g @qvac/cli 2>/dev/null || npm install -g @qvac/cli; \
	fi
	@echo -e "${GREEN}>> Core tools installed.${NC}"

setup: install-deps ## Set up Python backend (uv) and Nuxt frontend (bun)
	@echo -e "${GREEN}>> Setting up backend virtualenv with uv...${NC}"
	@cd backend && uv sync
	@echo -e "${GREEN}>> Installing frontend dependencies with bun...${NC}"
	@cd frontend && bun install
	@chmod +x scripts/*.sh
	@echo -e "${GREEN}>> Setup complete.${NC}"

setup-db: ## Install & start local PostgreSQL 16 and Neo4j via Homebrew
	@echo -e "${GREEN}>> Installing & starting PostgreSQL 16 and Neo4j...${NC}"
	@HOMEBREW_NO_AUTO_UPDATE=1 brew install postgresql@16 neo4j || true
	@brew services start postgresql@16 || true
	@neo4j start 2>/dev/null || brew services start neo4j || true
	@echo -e "${GREEN}>> Initializing PostgreSQL database 'synapse_state'...${NC}"
	@/opt/homebrew/opt/postgresql@16/bin/createuser -s synapse 2>/dev/null || true
	@/opt/homebrew/opt/postgresql@16/bin/createdb -U synapse synapse_state 2>/dev/null || true
	@psql -U synapse -d synapse_state -f backend/app/db/init.sql 2>/dev/null || true
	@echo -e "${GREEN}>> Databases ready.${NC}"

qvac: ## Start native QVAC inference server with Apple Silicon Metal GPU (:11434)
	@./scripts/qvac-mac-host-serve.sh

backend: ## Run FastAPI backend natively on http://127.0.0.1:8000
	@cd backend && \
	export RAG_DIR="$(PWD)/volumes/rag" && \
	export POSTGRES_DSN="$${POSTGRES_DSN:-postgresql://synapse:synapse-local-dev@127.0.0.1:5432/synapse_state}" && \
	export NEO4J_URI="$${NEO4J_URI:-bolt://127.0.0.1:7687}" && \
	export QVAC_BASE_URL="$${QVAC_BASE_URL:-http://127.0.0.1:11434}" && \
	mkdir -p "$$RAG_DIR" && \
	uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload

frontend: ## Run Nuxt frontend dev server on http://127.0.0.1:3001
	@cd frontend && bun run dev -- --port 3001

gateway: ## Run Caddy gateway on http://localhost:3000
	@caddy run --config gateway/Caddyfile.local

dev: ## Start full local stack without Docker (Metal QVAC + Backend + Frontend + Gateway)
	@./scripts/dev-local.sh

test: ## Run backend pytest suite
	@cd backend && uv run pytest

seed: ## Seed synthetic hospital & equipment graph data
	@uv run --project backend python data/synthetic/seed.py

stop: ## Stop any local dev processes on ports 3000, 3001, 8000, 11434
	@echo -e "${YELLOW}>> Stopping processes on ports 3000, 3001, 8000, 11434...${NC}"
	@for port in 3000 3001 8000 11434; do \
		pids=$$(lsof -ti :$$port 2>/dev/null || true); \
		if [ -n "$$pids" ]; then \
			echo "Killing PID(s) on port $$port: $$pids"; \
			kill -9 $$pids 2>/dev/null || true; \
		fi \
	done
	@echo -e "${GREEN}>> Cleaned up.${NC}"

clean: ## Clean build caches, temporary logs, and venvs
	@rm -rf backend/.venv backend/__pycache__ frontend/.nuxt frontend/.output
	@echo -e "${GREEN}>> Clean complete.${NC}"
