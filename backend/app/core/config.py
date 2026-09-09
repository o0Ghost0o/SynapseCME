from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "synapse-local-dev"
    postgres_dsn: str = "postgresql://synapse:synapse-local-dev@localhost:5432/synapse_state"

    qvac_base_url: str = "http://localhost:11434"
    medpsy_model: str = "medpsy:q4_k_m"
    embed_model: str = "bge-m3"

    stt_base_url: str = "http://stt:8000"
    stt_model: str = "Systran/faster-whisper-small"

    cors_origins: str = "*"

    # Auth. Defaults are development-only; the app logs loud warnings when
    # they are used.
    jwt_secret: str = "synapse-dev-jwt-secret-cambiame-2026"
    admin_user: str = "admin"
    admin_password: str = "synapse-admin"
    access_token_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_days: int = 7


settings = Settings()
