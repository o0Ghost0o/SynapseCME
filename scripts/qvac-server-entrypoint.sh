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
# Model reference resolution (Phase 2 — P2P model distribution baseline):
#   1. Local GGUF:  /models/<base>.gguf (bind-mounted drop zone) wins.
#   2. P2P/HTTP:    QVAC_MODEL_SOURCE (any Pear or HTTP URL, e.g. a HuggingFace
#                   resolve URL or a peer's model address) — QVAC fetches the
#                   model from the source on first start and caches it in its
#                   model store, so later boots use the local copy.
#   3. Registry:    the bare model name (must exist on the model registry).
# NOTE: the config "model" field accepting a URL/path could not be verified
# offline for every CLI version; adjust resolve_ref below if yours differs.
resolve_ref() {
    model="$1"
    base="${model%%:*}"
    if [ -f "/models/${base}.gguf" ]; then
        echo "QVAC: $model -> local /models/${base}.gguf" >&2
        printf '/models/%s.gguf' "$base"
    elif [ -n "$QVAC_MODEL_SOURCE" ] && printf '%s' "$QVAC_MODEL_SOURCE" | grep -q "$base"; then
        echo "QVAC: $model -> $QVAC_MODEL_SOURCE (P2P/HTTP fetch on first start)" >&2
        printf '%s' "$QVAC_MODEL_SOURCE"
    else
        if [ -n "$QVAC_MODEL_SOURCE" ]; then
            echo "QVAC: WARNING QVAC_MODEL_SOURCE does not mention '$base'; using registry name" >&2
        fi
        echo "QVAC: $model -> registry name (must exist on the registry)" >&2
        printf '%s' "$model"
    fi
}

medpsy_base="${MEDPSY_MODEL%%:*}"
medpsy_ref="$(resolve_ref "$MEDPSY_MODEL")"
embed_ref="$(resolve_ref "$EMBED_MODEL")"

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
        "model": "${embed_ref}",
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
