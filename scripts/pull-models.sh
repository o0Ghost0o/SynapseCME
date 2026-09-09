#!/usr/bin/env bash
# Pull the model stack onto the QVAC/Ollama node.
# Target GPU: NVIDIA GeForce RTX 3060 Ti (8 GB VRAM).
# Budget: MedPsy Q4_K_M (~4.5 GB) + bge-m3 (~0.5 GB) <= 6 GB resident.
set -euo pipefail

QVAC_URL="${QVAC_URL:-http://localhost:11434}"
MEDPSY_MODEL="${MEDPSY_MODEL:-medpsy:q4_k_m}"
EMBED_MODEL="${EMBED_MODEL:-bge-m3}"

pull() {
  echo ">> pulling $1"
  curl -sf -X POST "$QVAC_URL/api/pull" -d "{\"name\": \"$1\"}"
  echo
}

pull "$MEDPSY_MODEL"
pull "$EMBED_MODEL"

echo ">> installed models:"
curl -sf "$QVAC_URL/api/tags"
