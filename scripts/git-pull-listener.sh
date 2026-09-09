#!/usr/bin/env bash
# git-pull-listener: watch the upstream of the currently checked-out branch
# (origin/<branch>); on new commits pull and refresh the Docker stack,
# notifying a Discord webhook about each deployment.
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

BRANCH="$(git branch --show-current)"
if [ -z "$BRANCH" ]; then
  log "ERROR: HEAD detached; el listener necesita un branch checked out. Saliendo."
  exit 1
fi
if ! git rev-parse --verify "refs/remotes/origin/$BRANCH" >/dev/null 2>&1; then
  log "WARN: no existe origin/$BRANCH; se intentará con git pull --ff-only de todos modos"
fi
log "Escuchando cambios en origin/$BRANCH cada ${INTERVAL}s (repo: $REPO_DIR)"

while true; do
  # `git fetch origin` (sin refspec) actualiza TODAS las remote-tracking refs;
  # `git fetch origin main` solo escribe FETCH_HEAD y jamás movería origin/*.
  if ! git fetch origin 2>&1; then
    log "WARN: fetch falló (¿sin red?); reintentando en ${INTERVAL}s"
    sleep "$INTERVAL"
    continue
  fi

  remote_ref="refs/remotes/origin/$BRANCH"
  if ! git rev-parse --verify "$remote_ref" >/dev/null 2>&1; then
    log "WARN: $remote_ref no existe tras el fetch; reintentando en ${INTERVAL}s"
    sleep "$INTERVAL"
    continue
  fi

  local_head="$(git rev-parse HEAD)"
  remote_head="$(git rev-parse "$remote_ref")"

  if [ "$local_head" != "$remote_head" ]; then
    n_commits="$(git rev-list --count HEAD.."$remote_ref")"
    pending="$(git log --oneline --max-count=5 HEAD.."$remote_ref" | sed 's/^/  /')"
    [ "$n_commits" -gt 5 ] && pending="$pending\n  … y $((n_commits - 5)) más"
    notify_discord "$(printf '🚀 **Desplegando SynapseCME** (%s) — %d commit(s) nuevos:\n```\n%s\n```' "$BRANCH" "$n_commits" "$pending")"
    log "Nuevos commits en $remote_ref: $n_commits"

    if ! git pull --ff-only 2>&1; then
      log "ERROR: pull --ff-only rechazado (¿commits locales sin push?); se omite este ciclo"
      notify_discord "⚠️ **Despliegue abortado** — pull --ff-only rechazado en $BRANCH (¿hay commits locales sin push?)."
      sleep "$INTERVAL"
      continue
    fi

    log "Actualizando contenedores..."
    # --force-recreate: sin esto, cambios solo en scripts/ montados por volumen
    # (p.ej. el entrypoint de qvac) no recrean el contenedor y el deploy no aplica.
    compose_out="$(docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build --force-recreate 2>&1)"
    compose_rc=$?
    # Always flush the full output to the log.
    printf '%s\n' "$compose_out" | while IFS= read -r line; do log "compose: $line"; done

    if [ "$compose_rc" -eq 0 ]; then
      log "OK: stack actualizado"
      notify_discord "✅ **Despliegue exitoso** — SynapseCME actualizado (\`$(git rev-parse --short HEAD)\`)."
    else
      log "ERROR: docker compose up falló (rc=$compose_rc)"
      tail_lines="$(printf '%s\n' "$compose_out" | tail -n 15 | sed 's/`/ʼ/g')"
      notify_discord "$(printf '❌ **Despliegue falló** (rc=%s):\n```\n%s\n```' "$compose_rc" "$tail_lines")"
    fi
  fi

  sleep "$INTERVAL"
done
