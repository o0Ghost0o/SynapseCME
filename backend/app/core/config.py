from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "synapse-local-dev"
    postgres_dsn: str = "postgresql://synapse:synapse-local-dev@localhost:5432/synapse_state"

    qvac_base_url: str = "http://4.0.0.3:11434"
    medpsy_model: str = "medpsy:q4_k_m"
    # QVAC SDK constant (built-in, verified to load). bge-m3 also works but
    # only through a GGUF the QVAC embeddings addon accepts (drop it in
    # ./models/ or set QVAC_MODEL_SOURCE).
    embed_model: str = "EMBEDDINGGEMMA_300M_Q4_0"

    rag_dir: str = "/data/rag"
    rag_top_k: int = 3

    stt_base_url: str = "http://stt:8000"
    stt_model: str = "Systran/faster-whisper-small"

    cors_origins: str = "*"

    # Phase 3 — node-to-node observation sync. Empty sync_token = endpoint
    # closed; empty sync_peers = nothing is enqueued or pushed.
    sync_peers: str = ""
    sync_token: str = ""
    sync_interval_s: int = 30

    # Auth. Defaults are development-only; the app logs loud warnings when
    # they are used.
    jwt_secret: str = "synapse-dev-jwt-secret-cambiame-2026"
    admin_user: str = "admin"
    admin_password: str = "synapse-admin"
    access_token_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_days: int = 7


settings = Settings()
