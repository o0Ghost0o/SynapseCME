# QVAC integration spec — 4 phases

Status: phase 0–1 implemented on `feat/qvac-core`; 2–3 functional baseline.

Context: today "QVAC" in this repo is stock Ollama renamed (`ollama/ollama:latest`
in compose, an Ollama-NDJSON httpx client in `backend/app/agent/qvac.py`). The real
QVAC is Tether's local AI SDK (`tetherto-qvac-sdk` Python / `@qvac/sdk` JS) with an
OpenAI-compatible HTTP server (`qvac serve openai`, port 11434) and native P2P
(model distribution between peers, blind relays, delegated inference).
Docs: https://docs.qvac.tether.io/ · https://github.com/tetherto/qvac

Design rule for the whole effort: **QVAC is the single inference core**. Ollama
stays only as an opt-in fallback (compose profile `ollama`), never the default.

## Phase 0 — QVAC as the inference node

- Compose: new `qvac` service running the QVAC HTTP server (Node 22 + `@qvac/cli`,
  `qvac serve openai`), models declared in `qvac.config.json`, GGUF import from the
  existing `./models` bind mount, GPU via `docker-compose.gpu.yml`. Old Ollama
  service moves to profile `ollama` (off by default).
- Backend: `QvacClient` rewritten against the OpenAI-compatible API
  (`POST /v1/chat/completions` SSE, `GET /v1/models`, `POST /v1/embeddings`).
  Token usage comes from the standard `usage` object; the Ollama-isms (`/api/ps`
  cold-start probe, NDJSON chunks) are dropped. `qvac_base_url` gains a `/v1` path
  convention handled by the client.
- Config: `app/core/config.py` keeps `qvac_base_url`; adds QVAC model ids.
- Tests: `tests/test_agent.py` mocks the OpenAI SSE stream instead of Ollama NDJSON.

## Phase 1 — real GraphRAG (embeddings + retrieval in the loop)

- `app/agent/rag.py`: embedding texts via `POST /v1/embeddings` (QVAC embed
  model; default `EMBEDDINGGEMMA_300M_Q4_0` built-in constant), a
  LanceDB index over observation texts + equipment summaries (persisted under
  `VOLUMES_ROOT`), retrieval of top-k neighbors for a message.
- `app/graph/context.py`: graph-neighborhood context (facility → equipment →
  states, recent observations) fetched from Neo4j when a facility is known.
- `service.handle_chat`: retrieved context is injected into the extraction system
  prompt (marked as prior knowledge, with instruction not to invent); retrieval
  failures degrade silently to the current behavior. The dead `QvacClient.embed()`
  path is replaced by the wired one.

## Phase 2 — P2P model distribution (baseline)

- `qvac.config.json` models resolve from, in order: local store → `./models/*.gguf`
  → P2P/HTTP source (`QVAC_MODEL_SOURCE` in `.env`, any Pear/HTTP URL e.g.
  HuggingFace). New field nodes fetch MedPsy from a peer instead of a registry.
- Honest limits: delegated inference (weak device → peer GPU) and the DHT-style
  model registry are QVAC SDK features we do not wrap yet; the server config is
  P2P-ready and the seam is `scripts/qvac-entrypoint.sh`.

## Phase 3 — node-to-node observation sync (baseline)

- `app/sync/` module: static peer list (`SYNC_PEERS` in `.env`), node identity
  (`node_id` UUID persisted in Postgres), outbox of transactions flagged for sync,
  background pusher that POSTs new extractions to peers' `/api/sync/ingest`.
- `POST /api/sync/ingest`: authenticated by shared `SYNC_TOKEN`, applies incoming
  extractions through the existing `engine.ingest_extraction` (idempotent MERGE +
  consensus votes), so converging states work across nodes.
- Honest limits: no gossip/discovery, no conflict resolution beyond the existing
  vote-consensus, no CRDT ordering. Static peers + at-least-once delivery.

## Out of scope (documented, not built)

Delegated inference topics, DHT peer discovery, decentralized training/fine-tuning,
multimodal/voice capture (QVAC supports them; the hooks are the same OpenAI API).
