#!/usr/bin/env bash
# Report/refresh the models served by the QVAC node.
# The OpenAI-compatible API has no pull endpoint — models are downloaded
# automatically by the server at startup (see scripts/qvac-server-entrypoint.sh
# and scripts/qvac.config.json). This script just verifies what the node
# currently serves.
set -euo pipefail

QVAC_URL="${QVAC_URL:-http://localhost:11434}"

echo ">> models served by $QVAC_URL:"
curl -sf "$QVAC_URL/v1/models" | jq .
echo
echo ">> note: no pull endpoint exists on the OpenAI-compatible API."
echo ">> Models download automatically when the QVAC server starts."
echo ">> Drop a GGUF into ./models/ or set QVAC_MODEL_SOURCE (Phase 2) for P2P fetch."
