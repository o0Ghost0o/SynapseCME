#!/usr/bin/env bash
# git-pull-listener: watch origin/main; on new commits pull and refresh the
# Docker stack. Run as a systemd user service (see
# ~/.config/systemd/user/synapse-pull-listener.service).
#
# Usage: git-pull-listener.sh [poll-interval-seconds]
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERVAL="${1:-60}"

cd "$REPO_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "Escuchando cambios en origin/main cada ${INTERVAL}s (repo: $REPO_DIR)"

while true; do
  if ! git fetch origin main 2>&1; then
    log "WARN: fetch falló (¿sin red?); reintentando en ${INTERVAL}s"
    sleep "$INTERVAL"
    continue
  fi

  local_head="$(git rev-parse main)"
  remote_head="$(git rev-parse origin/main)"

  if [ "$local_head" != "$remote_head" ]; then
    log "Nuevos commits en origin/main: $(git rev-list --count main..origin/main)"
    if ! git merge --ff-only origin/main; then
      log "ERROR: merge --ff-only rechazado (¿commits locales?); se omite este ciclo"
      sleep "$INTERVAL"
      continue
    fi
    log "Actualizando contenedores..."
    if docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build; then
      log "OK: stack actualizado"
    else
      log "ERROR: docker compose up falló"
    fi
  fi

  sleep "$INTERVAL"
done
