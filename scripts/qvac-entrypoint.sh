#!/bin/sh
# QVAC node entrypoint — starts Ollama and auto-pulls the model stack
# (MedPsy Q4_K_M + bge-small) if the persistent volume doesn't have them.
# Models persist in the qvac_models volume, so pulls happen once per node.

set -u

MODELS="${MEDPSY_MODEL:-medpsy:q4_k_m} ${EMBED_MODEL:-bge-m3}"

pull_or_import() {
    model="$1"
    base="${model%%:*}"
    # ollama list always shows an explicit tag (defaults to :latest)
    case "$model" in *:*) ;; *) model="$model:latest" ;; esac
    if ollama list | awk 'NR > 1 {print $1}' | grep -qx "$model"; then
        echo "QVAC: $model already present"
        return 0
    fi
    echo "QVAC: pulling $model ..."
    if ollama pull "$model"; then
        return 0
    fi
    # Not in the registry (e.g. MedPsy) — import a local GGUF if one is
    # mounted at /models/<name>.gguf.
    if [ -f "/models/$base.gguf" ]; then
        echo "QVAC: importing /models/$base.gguf as $base"
        printf 'FROM /models/%s.gguf\n' "$base" > /tmp/Modelfile.qvac
        ollama create "$base" -f /tmp/Modelfile.qvac
        return $?
    fi
    echo "QVAC: WARNING could not obtain $model (pull failed, no /models/$base.gguf); Ollama retries on first use" >&2
    return 1
}

ollama serve &
SERVE_PID=$!
trap 'kill -TERM "$SERVE_PID" 2>/dev/null' TERM INT

# Wait for the local API to come up (max ~2 min).
i=0
until ollama list >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -gt 60 ]; then
        echo "QVAC: API did not come up; skipping auto-pull" >&2
        break
    fi
    sleep 2
done

if ollama list >/dev/null 2>&1; then
    for model in $MODELS; do
        pull_or_import "$model"
    done
fi

wait "$SERVE_PID"
