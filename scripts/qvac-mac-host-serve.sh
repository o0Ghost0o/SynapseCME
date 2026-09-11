#!/usr/bin/env bash
# QVAC inference server on macOS host with Apple Silicon Metal GPU acceleration.
#
# Runs @qvac/cli natively on macOS to leverage Apple Silicon GPU via Metal and
# unified memory, serving an OpenAI-compatible API on port 11434 to Docker.
#
# Prerequisite:
#   Node.js 18+ and @qvac/cli:
#     brew install node
#     npm install -g @qvac/cli
#
# Usage:
#   ./scripts/qvac-mac-host-serve.sh
#
# Stop:
#   kill $(lsof -t -i:11434)  or  Ctrl+C

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_PATH="$SCRIPT_DIR/qvac.mac.config.json"
MODELS_DIR="$REPO_ROOT/models"

# 1) System check -------------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"

if [ "$OS" != "Darwin" ]; then
    echo "ERROR: This script is intended for macOS (Darwin). Current OS: $OS" >&2
    exit 1
fi

if [ "$ARCH" = "arm64" ]; then
    CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Apple Silicon")
    echo ">> Detected $CHIP ($ARCH) — Metal GPU acceleration available"
else
    echo "WARNING: Running on $ARCH (x86_64). Metal GPU requires Apple Silicon (arm64); inference will run on CPU." >&2
fi

# 2) Load .env if present -----------------------------------------------------
if [ -f "$REPO_ROOT/.env" ]; then
    # shellcheck disable=SC1091
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

MEDPSY_MODEL="${MEDPSY_MODEL:-medpsy:q4_k_m}"
EMBED_MODEL="${EMBED_MODEL:-EMBEDDINGGEMMA_300M_Q4_0}"
QVAC_MODEL_SOURCE="${QVAC_MODEL_SOURCE:-https://huggingface.co/qvac/MedPsy-1.7B-GGUF/resolve/main/medpsy-1.7b-q4_k_m-imat.gguf}"

# 3) Locate qvac CLI binary ---------------------------------------------------
QVAC_BIN=""
if command -v qvac >/dev/null 2>&1; then
    QVAC_BIN="$(command -v qvac)"
elif [ -f "$HOME/.bun/bin/qvac" ]; then
    QVAC_BIN="$HOME/.bun/bin/qvac"
elif [ -f "$HOME/.local/bin/qvac" ]; then
    QVAC_BIN="$HOME/.local/bin/qvac"
elif [ -f "/opt/homebrew/bin/qvac" ]; then
    QVAC_BIN="/opt/homebrew/bin/qvac"
fi

if [ -z "$QVAC_BIN" ]; then
    echo "ERROR: 'qvac' CLI not found." >&2
    echo "To install on macOS with Bun:" >&2
    echo "  bun install -g @qvac/cli" >&2
    exit 1
fi

echo ">> Using QVAC binary: $QVAC_BIN"

# 4) Generate qvac.mac.config.json dynamically --------------------------------
emit_model_entry() {
    alias="$1"
    kind="$2"
    ctx="$3"
    base="${alias%%:*}"

    if [ "$kind" = "llm" ]; then
        cfg=$(printf ', "config": {"ctx_size": %s}' "$ctx")
    else
        cfg=""
    fi

    if [ -f "$MODELS_DIR/${base}.gguf" ]; then
        echo ">> Model '$alias' -> local file: $MODELS_DIR/${base}.gguf" >&2
        src=$(printf '"%s/%s.gguf"' "$MODELS_DIR" "$base")
        printf '"%s": {"src": %s, "type": "%s"%s}' "$alias" "$src" "$kind" "$cfg"
    elif [ -n "$QVAC_MODEL_SOURCE" ] && printf '%s' "$QVAC_MODEL_SOURCE" | grep -q "$base"; then
        echo ">> Model '$alias' -> remote URL: $QVAC_MODEL_SOURCE (fetched on first load)" >&2
        src=$(printf '"%s"' "$QVAC_MODEL_SOURCE")
        printf '"%s": {"src": %s, "type": "%s"%s}' "$alias" "$src" "$kind" "$cfg"
    elif printf '%s' "$base" | grep -qE '^[A-Z0-9_]+$'; then
        echo ">> Model '$alias' -> SDK built-in constant" >&2
        printf '"%s": {"model": "%s"%s}' "$alias" "$alias" "$cfg"
    else
        echo "WARNING: No local GGUF in $MODELS_DIR, no QVAC_MODEL_SOURCE, and not an SDK constant for '$alias'." >&2
        printf ''
    fi
}

mkdir -p "$MODELS_DIR"

medpsy_entry="$(emit_model_entry "$MEDPSY_MODEL" llm 8192)"
embed_entry="$(emit_model_entry "$EMBED_MODEL" embeddings 8192)"

entries=""
if [ -n "$medpsy_entry" ]; then
    entries="$medpsy_entry"
fi
if [ -n "$embed_entry" ]; then
    if [ -n "$entries" ]; then
        entries="$entries,
      $embed_entry"
    else
        entries="$embed_entry"
    fi
fi

cat > "$CONFIG_PATH" <<EOF
{
  "serve": {
    "models": {
      ${entries}
    },
    "load": {
      "timeoutMs": 600000,
      "cancelOnDisconnect": false
    }
  }
}
EOF

echo ">> Config generated at $CONFIG_PATH:"
cat "$CONFIG_PATH"
echo ""

# 5) Free port 11434 if previously held by node/qvac ---------------------------
PORT=11434
PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    echo ">> Port $PORT is occupied by PID(s): $PIDS"
    for pid in $PIDS; do
        pname=$(ps -p "$pid" -o comm= 2>/dev/null || true)
        if [[ "$pname" == *"node"* || "$pname" == *"qvac"* ]]; then
            echo "   Stopping previous QVAC node process (PID $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 1
        else
            echo "WARNING: Port $PORT is held by $pname (PID $pid). If not QVAC, please stop it before continuing." >&2
        fi
    done
fi

# 6) Serve --------------------------------------------------------------------
echo ">> Starting native QVAC OpenAI-compatible server on 0.0.0.0:$PORT..."
echo ">> Press Ctrl+C to stop."
exec "$QVAC_BIN" serve --openai --no-default --allow-unauthenticated \
    -c "$CONFIG_PATH" \
    --host 0.0.0.0 --port "$PORT"
