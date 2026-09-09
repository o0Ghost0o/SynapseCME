#!/usr/bin/env bash
# git-pull-listener: watch origin/main; on new commits check out main, pull
# and refresh the Docker stack, notifying a Discord webhook about each
# deployment. Only main is ever deployed — other branches are ignored.
# Run as a systemd user service (see
# ~/.config/systemd/user/synapse-pull-listener.service).
#
# Usage: git-pull-listener.sh [poll-interval-seconds]
#
# Discord: set DISCORD_DEPLOY_WEBHOOK in the repo-root .env (gitignored).
set -uo pipefail

INTERVAL="${1:-60}"
REPO_DIR="${2:-}"
if [ -z "$REPO_DIR" ]; then
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# Copia estable de ejecución: el deploy hace `git merge --ff-only`, que puede
# REESCRIBIR este mismo archivo mientras bash lo está ejecutando. Bash lee los
# scripts de forma incremental por OFFSET de bytes, así que el contenido nuevo
# desalinea la ejecución y silenció el resto del ciclo. Por eso SIEMPRE se
# corre desde una copia privada; tras un deploy que tocó el script, se re-exec.
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}"
RUNNING_COPY="$STATE_DIR/synapsecme-pull-listener.run"
if [ "${BASH_SOURCE[0]}" != "$RUNNING_COPY" ]; then
  mkdir -p "$STATE_DIR"
  cp "${BASH_SOURCE[0]}" "$RUNNING_COPY"
  exec bash "$RUNNING_COPY" "$INTERVAL" "$REPO_DIR"
fi

maybe_reexec() {
  if ! cmp -s "$REPO_DIR/scripts/git-pull-listener.sh" "$RUNNING_COPY" 2>/dev/null; then
    log "El script cambió con el deploy; re-ejecutando la nueva versión..."
    cp "$REPO_DIR/scripts/git-pull-listener.sh" "$RUNNING_COPY"
    exec bash "$RUNNING_COPY" "$INTERVAL" "$REPO_DIR"
  fi
}

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

# CI/CD fijo: solo main se escucha y solo main se despliega.
BRANCH="main"
if ! git rev-parse --verify "refs/remotes/origin/$BRANCH" >/dev/null 2>&1; then
  log "WARN: no existe origin/$BRANCH aún; se creará con el primer fetch"
fi
# El estado desplegado se compara contra origin/main vía un archivo de estado,
# no contra el branch local: si se hace push desde ESTA máquina, el branch
# local ya está actualizado y una comparación local-vs-remote nunca dispararía
# el deploy.
STATE_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/synapsecme-deployed.sha"
mkdir -p "$(dirname "$STATE_FILE")"
log "Escuchando cambios en origin/$BRANCH cada ${INTERVAL}s (repo: $REPO_DIR, estado: $STATE_FILE)"

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
  remote_head="$(git rev-parse "$remote_ref")"

  deployed_sha=""
  [ -f "$STATE_FILE" ] && deployed_sha="$(tr -d '[:space:]' < "$STATE_FILE")"
  if [ -z "$deployed_sha" ]; then
    # Primera corrida (o estado perdido): tomar el HEAD actual como base sin
    # desplegar; el próximo commit nuevo dispara el deploy.
    deployed_sha="$remote_head"
    printf '%s\n' "$remote_head" > "$STATE_FILE"
    log "Sin estado previo de despliegue; base = $(git rev-parse --short "$remote_head"). El próximo commit nuevo dispara deploy."
  fi

  if [ "$deployed_sha" != "$remote_head" ]; then
    if git cat-file -e "$deployed_sha^{commit}" 2>/dev/null; then
      n_commits="$(git rev-list --count "$deployed_sha..$remote_head" 2>/dev/null || echo "?")"
      pending="$(git log --oneline --max-count=5 "$deployed_sha..$remote_head" 2>/dev/null | sed 's/^/  /')"
    else
      n_commits="?"
      pending="  (SHA previo desconocido: $deployed_sha)"
    fi
    [ "$n_commits" != "?" ] && [ "$n_commits" -gt 5 ] && pending="$pending\n  … y $((n_commits - 5)) más"
    notify_discord "$(printf '🚀 **Desplegando SynapseCME** (%s) — %s commit(s) nuevos:\n```\n%s\n```' "$BRANCH" "$n_commits" "$pending")"
    log "origin/$BRANCH avanzó: $deployed_sha -> $remote_head ($n_commits commits)"

    # Asegurar checkout en main antes de actualizar: nunca se despliega
    # desde otro branch, esté o no esté checkout-eado en el repo.
    if [ "$(git branch --show-current)" != "$BRANCH" ]; then
      log "Cambiando de $(git branch --show-current) a $BRANCH..."
      if ! git checkout "$BRANCH" 2>&1; then
        log "ERROR: no se pudo hacer checkout de $BRANCH; se omite este ciclo"
        notify_discord "⚠️ **Despliegue abortado** — no se pudo hacer checkout de \`$BRANCH\` (¿working tree sucio?)."
        sleep "$INTERVAL"
        continue
      fi
    fi

    if ! git merge --ff-only "$remote_ref" 2>&1; then
      log "ERROR: merge --ff-only rechazado (¿commits locales sin push?); se omite este ciclo"
      notify_discord "⚠️ **Despliegue abortado** — merge --ff-only rechazado en $BRANCH (¿hay commits locales sin push?)."
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
      printf '%s\n' "$remote_head" > "$STATE_FILE"
      notify_discord "✅ **Despliegue exitoso** — SynapseCME actualizado (\`$(git rev-parse --short HEAD)\`)."
    else
      # No se actualiza el estado: el próximo ciclo reintenta el mismo commit.
      log "ERROR: docker compose up falló (rc=$compose_rc)"
      tail_lines="$(printf '%s\n' "$compose_out" | tail -n 15 | sed 's/`/ʼ/g')"
      notify_discord "$(printf '❌ **Despliegue falló** (rc=%s):\n```\n%s\n```' "$compose_rc" "$tail_lines")"
    fi

    # Si el deploy trajo una versión nueva de este script, seguir ejecutando
    # la copia antigua desalinearía bash; se adopta la nueva versión.
    maybe_reexec
  fi

  sleep "$INTERVAL"
done
