#!/usr/bin/env bash
# QVAC server entrypoint (Phase 0) — real QVAC (Tether) OpenAI-compatible
# HTTP server via @qvac/cli, replacing the stock Ollama container.
#
# Responsibilities:
#   1. Install @qvac/cli globally on first boot (npm cache volume makes
#      re-installs on later boots cheap; the binary lives in the named
#      qvac_models volume so it also survives container recreation).
#   2. Generate /config/qvac.config.json from env vars. The CLI cannot
#      template env vars into the config itself, so we render it here.
#   3. exec "qvac serve openai" bound to 0.0.0.0:11434.
#
# NOTE (uncertain, verify against the installed CLI version): the exact
# flags of `qvac serve openai` and the config key semantics for a local
# GGUF path could not be verified offline. We pass --host/--port and
# QVAC_CONFIG_PATH; if your version disagrees, adjust below. The config
# shape used is the documented one:
#   {"serve": {"models": {"<name>": {"model": "<id|path>", "default": true,
#    "config": {"ctx_size": 4096}}}}

set -u

QVAC_PORT="${QVAC_PORT:-11434}"
QVAC_HOST="${QVAC_HOST:-0.0.0.0}"
MEDPSY_MODEL="${MEDPSY_MODEL:-medpsy:q4_k_m}"
EMBED_MODEL="${EMBED_MODEL:-bge-m3}"
QVAC_MODEL_SOURCE="${QVAC_MODEL_SOURCE:-}"
CONFIG_DIR="/config"
CONFIG_PATH="${CONFIG_DIR}/qvac.config.json"

# 1) CLI --------------------------------------------------------------------
if ! command -v qvac >/dev/null 2>&1; then
    echo "QVAC: installing @qvac/cli ..."
    npm install -g @qvac/cli
fi
qvac --version 2>/dev/null || echo "QVAC: qvac binary present"

# 2) Config -------------------------------------------------------------------
medpsy_base="${MEDPSY_MODEL%%:*}"
medpsy_ref="$MEDPSY_MODEL"

# Prefer a local GGUF dropped into ./models (mounted at /models, ro) when the
# file matches the model name. The config's "model" field is set to the file
# path; if your QVAC version wants a different key (e.g. a "path"/"source"
# field) for local GGUFs, adjust here.
if [ -f "/models/${medpsy_base}.gguf" ]; then
    echo "QVAC: found local /models/${medpsy_base}.gguf — wiring it into the config"
    medpsy_ref="/models/${medpsy_base}.gguf"
fi
# shellcheck disable=SC2034
embed_ref="$EMBED_MODEL"
if [ -n "$QVAC_MODEL_SOURCE" ]; then
    echo "QVAC: QVAC_MODEL_SOURCE set ($QVAC_MODEL_SOURCE) — Phase 2 will use it for P2P fetch"
fi

mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_PATH" <<EOF
{
  "serve": {
    "models": {
      "${medpsy_base}": {
        "model": "${medpsy_ref}",
        "default": true,
        "config": {
          "ctx_size": 4096
        }
      },
      "${EMBED_MODEL}": {
        "model": "${EMBED_MODEL}",
        "config": {
          "ctx_size": 8192
        }
      }
    }
  }
}
EOF
echo "QVAC: wrote $CONFIG_PATH:"
cat "$CONFIG_PATH"

# 3) Serve --------------------------------------------------------------------
# Default bind is 127.0.0.1:11434 per the docs; the container needs 0.0.0.0.
export QVAC_CONFIG_PATH="$CONFIG_PATH"
exec qvac serve openai --host "$QVAC_HOST" --port "$QVAC_PORT"
