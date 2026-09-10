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

# 0) System libs ---------------------------------------------------------------
# The SDK's Bare addons (rocksdb-native, llm-llamacpp, ...) need shared libs
# that node:*-slim does not ship; the worker SIGABRTs without them (verified
# against @qvac/cli 0.13.0 on node:22-bookworm-slim). libvulkan1 also unlocks
# GPU acceleration where a Vulkan ICD is present.
# GPU note (verified on driver 570.211.01): the NVIDIA Vulkan ICD
# (libGLX_nvidia.so.0) dlopens libEGL.so.1 during init and refuses to
# initialize entirely (vk_icdNegotiateLoaderICDInterfaceVersion ->
# VK_ERROR_INITIALIZATION_FAILED, loader reports "Could not get
# 'vkCreateInstance' ... backend silently falls back to CPU) when libEGL
# is absent. node:*-slim ships neither it nor libGLX_nvidia's NEEDED X
# libs, so all four must be present before the ICD will load.
need_pkgs=""
for lib in libatomic1 libssl3 libvulkan1 libegl1 libxext6 libx11-6 libxcb1; do
    if ! dpkg -s "$lib" >/dev/null 2>&1; then
        need_pkgs="$need_pkgs $lib"
    fi
done
if [ -n "$need_pkgs" ]; then
    echo "QVAC: installing missing system libs:$need_pkgs"
    apt-get update -qq && apt-get install -y -qq --no-install-recommends $need_pkgs
fi

QVAC_PORT="${QVAC_PORT:-11434}"
QVAC_HOST="${QVAC_HOST:-0.0.0.0}"
MEDPSY_MODEL="${MEDPSY_MODEL:-medpsy:q4_k_m}"
EMBED_MODEL="${EMBED_MODEL:-bge-m3}"
QVAC_MODEL_SOURCE="${QVAC_MODEL_SOURCE:-}"
CONFIG_DIR="/config"
CONFIG_PATH="${CONFIG_DIR}/qvac.config.json"

# 1) CLI --------------------------------------------------------------------
# The package persists in the qvac_models volume (mounted over
# /usr/local/lib/node_modules) but the bin symlink at /usr/local/bin/qvac
# lives in the image layer and is lost on container recreation — relink it
# when the package is already there instead of reinstalling.
if ! command -v qvac >/dev/null 2>&1; then
    if [ -f /usr/local/lib/node_modules/@qvac/cli/dist/index.js ]; then
        echo "QVAC: relinking qvac binary from persisted module"
        ln -sf ../lib/node_modules/@qvac/cli/dist/index.js /usr/local/bin/qvac
    else
        echo "QVAC: installing @qvac/cli ..."
        npm install -g @qvac/cli
    fi
fi
qvac --version 2>/dev/null || echo "QVAC: qvac binary present"

# 2) Config -------------------------------------------------------------------
# serve.models entries, verified against @qvac/cli 0.13.0 (docs/serve/*):
#   - constant form:  {"model": "<SDK_CONSTANT>", "config": {...}}
#   - explicit form:  {"src": "<path|https://|registry://|pear://>", "type":
#                     "llm"|"embeddings", "config": {...}} — src is passed to
#                     the SDK as modelSrc verbatim (local GGUF, HuggingFace
#                     resolve URL, peer address, ...). The alias KEY must equal
#                     the model name the backend sends ("medpsy:q4_k_m", "bge-m3").
# Resolution order per model:
#   1. Local GGUF:  /models/<base>.gguf (bind-mounted drop zone) wins.
#   2. P2P/HTTP:    QVAC_MODEL_SOURCE (only if it mentions the model's base name).
#   3. SDK constant: ALL-CAPS/underscore name (e.g. LLAMA_3_2_1B_INST_Q4_0).
#   -> otherwise the model is NOT registered: the server stays up and the
#      backend falls back to the rule extractor / skips RAG.
emit_model_entry() {
    alias="$1"     # full model name = config alias key
    kind="$2"      # llm | embeddings
    ctx="$3"       # ctx_size for the llm engine config (embeddings reject it)
    base="${alias%%:*}"
    src=""
    # ctx is only valid for the llm addon (verified 0.13.0: embeddings
    # modelConfig rejects "ctx_size" with Unrecognized key).
    if [ "$kind" = "llm" ]; then
        cfg=$(printf ', "config": {"ctx_size": %s}' "$ctx")
    else
        cfg=""
    fi
    if [ -f "/models/${base}.gguf" ]; then
        echo "QVAC: $alias -> local /models/${base}.gguf" >&2
        src=$(printf '"/models/%s.gguf"' "$base")
    elif [ -n "$QVAC_MODEL_SOURCE" ] && printf '%s' "$QVAC_MODEL_SOURCE" | grep -q "$base"; then
        echo "QVAC: $alias -> $QVAC_MODEL_SOURCE (fetched on first load, then cached)" >&2
        src=$(printf '"%s"' "$QVAC_MODEL_SOURCE")
    elif printf '%s' "$base" | grep -qE '^[A-Z0-9_]+$'; then
        echo "QVAC: $alias -> SDK constant" >&2
        printf '"%s": {"model": "%s"%s}' "$alias" "$alias" "$cfg"
        return
    else
        echo "QVAC: WARNING no local GGUF, QVAC_MODEL_SOURCE, or SDK constant for '$alias' — not registering it (backend will use fallbacks)" >&2
        printf ''
        return
    fi
    printf '"%s": {"src": %s, "type": "%s"%s}' "$alias" "$src" "$kind" "$cfg"
}

entries=""
add_entry() {
    [ -z "$1" ] && return
    if [ -n "$entries" ]; then entries="$entries,"; fi
    entries="$entries
    $1"
}

add_entry "$(emit_model_entry "$MEDPSY_MODEL" llm 8192)"
add_entry "$(emit_model_entry "$EMBED_MODEL" embeddings 8192)"

mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_PATH" <<EOF
{
  "serve": {
    "models": {${entries}
    },
    "load": {
      "timeoutMs": 600000,
      "cancelOnDisconnect": false
    }
  }
}
EOF
echo "QVAC: wrote $CONFIG_PATH:"
cat "$CONFIG_PATH"

# 3) Serve --------------------------------------------------------------------
# Verified against @qvac/cli 0.13.0:
#   - `qvac serve openai` is deprecated -> `qvac serve --openai --no-default`
#   - config path goes via -c/--config (env QVAC_CONFIG_PATH is NOT read);
#     models are lazy-loaded on first request unless --model <alias> is passed
#   - binding a non-loopback host requires either --api-key/--api-key-file or
#     an explicit --allow-unauthenticated. The server only listens on the
#     internal compose network (backend + healthcheck), so unauthenticated is
#     acceptable here; put a real key in front before exposing the port.
# We deliberately do NOT pass --model: a bare registry name that fails to
# download must not crash the node at boot; lazy loading keeps the server up
# and the backend falls back to the rule extractor meanwhile.
# Default bind is 127.0.0.1:11434 per the docs; the container needs 0.0.0.0.
exec qvac serve --openai --no-default --allow-unauthenticated \
    -c "$CONFIG_PATH" \
    --host "$QVAC_HOST" --port "$QVAC_PORT"
