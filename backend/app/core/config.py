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

    rag_dir: str = "/data/rag"
    rag_top_k: int = 3

    cors_origins: str = "*"


settings = Settings()
