-- SynapseCME operational state store (PostgreSQL).
-- The graph lives in Neo4j; mutable operational state, metrics and the
-- transaction log live here.

CREATE TABLE IF NOT EXISTS equipment_state_log (
    id BIGSERIAL PRIMARY KEY,
    equipment_id TEXT NOT NULL,
    field TEXT NOT NULL,               -- e.g. 'manufacturer', 'age_years', 'exists'
    old_state TEXT,                    -- Desconocido | Estimado | Reportado | Confirmado
    new_state TEXT NOT NULL,
    confidence REAL,
    observation_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS perf_log (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    model TEXT NOT NULL,
    model_load_ms BIGINT,              -- model load time
    prompt_tokens INTEGER NOT NULL,
    generation_tokens INTEGER NOT NULL,
    ttft_ms BIGINT NOT NULL,           -- time to first token
    total_ms BIGINT NOT NULL,
    throughput_tps REAL NOT NULL,      -- tokens/sec
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every graph mutation / data exchange, shown live in the network view.
CREATE TABLE IF NOT EXISTS transaction_log (
    id BIGSERIAL PRIMARY KEY,
    actor TEXT NOT NULL,               -- contributor name or client id
    client_type TEXT,                  -- field_app | dashboard | executive | system
    action TEXT NOT NULL,              -- create | merge | promote | query | connect | disconnect
    target_type TEXT,                  -- Facility | Equipment | Observation | ...
    target_id TEXT,
    target_name TEXT,
    state_transition TEXT,             -- e.g. 'Estimado -> Reportado'
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tx_log_created ON transaction_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tx_log_action ON transaction_log (action);
CREATE INDEX IF NOT EXISTS idx_perf_log_created ON perf_log (created_at DESC);

-- Auth: users and refresh-token rotation. The backend also creates these
-- idempotently at startup (db.ensure_schema) for deployments whose data dir
-- was initialized before this file existed.
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'capturer', 'viewer')),
    password_hash TEXT NOT NULL,
    disabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens (user_id);
