#!/usr/bin/env bash
# git-pull-listener: watch origin/main; on new commits pull and refresh the
# Docker stack, notifying a Discord webhook about each deployment.
# Run as a systemd user service (see
# ~/.config/systemd/user/synapse-pull-listener.service).
#
# Usage: git-pull-listener.sh [poll-interval-seconds]
#
# Discord: set DISCORD_DEPLOY_WEBHOOK in the repo-root .env (gitignored).
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERVAL="${1:-60}"

cd "$REPO_DIR"

# Webhook URL and other local overrides live in .env (never committed).
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

notify_discord() {
  local content="$1"
  [ -n "${DISCORD_DEPLOY_WEBHOOK:-}" ] || return 0
  jq -n --arg content "$content" '{content: $content}' \
    | curl -sS -o /dev/null -w '%{http_code}' -X POST \
        -H 'Content-Type: application/json' \
        --data-binary @- "$DISCORD_DEPLOY_WEBHOOK" \
    | grep -q '^2' || log "WARN: no se pudo enviar notificación a Discord"
}

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
    n_commits="$(git rev-list --count main..origin/main)"
    pending="$(git log --oneline --max-count=5 main..origin/main | sed 's/^/  /')"
    [ "$n_commits" -gt 5 ] && pending="$pending\n  … y $((n_commits - 5)) más"
    notify_discord "$(printf '🚀 **Desplegando SynapseCME** — %d commit(s) nuevos:\n```\n%s\n```' "$n_commits" "$pending")"
    log "Nuevos commits en origin/main: $n_commits"

    if ! git merge --ff-only origin/main; then
      log "ERROR: merge --ff-only rechazado (¿commits locales?); se omite este ciclo"
      notify_discord "⚠️ **Despliegue abortado** — merge --ff-only rechazado (¿hay commits locales sin push?)."
      sleep "$INTERVAL"
      continue
    fi

    log "Actualizando contenedores..."
    compose_out="$(docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build 2>&1)"
    compose_rc=$?
    # Always flush the full output to the log.
    printf '%s\n' "$compose_out" | while IFS= read -r line; do log "compose: $line"; done

    if [ "$compose_rc" -eq 0 ]; then
      log "OK: stack actualizado"
      notify_discord "✅ **Despliegue exitoso** — SynapseCME actualizado (\`$(git rev-parse --short main)\`)."
    else
      log "ERROR: docker compose up falló (rc=$compose_rc)"
      tail_lines="$(printf '%s\n' "$compose_out" | tail -n 15 | sed 's/`/ʼ/g')"
      notify_discord "$(printf '❌ **Despliegue falló** (rc=%s):\n```\n%s\n```' "$compose_rc" "$tail_lines")"
    fi
  fi

  sleep "$INTERVAL"
done
