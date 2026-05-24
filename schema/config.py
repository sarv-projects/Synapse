from functools import lru_cache
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    neo4j_uri: str = Field(default=...)
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")
    neo4j_database: str = Field(default="neo4j")

    # LLM providers
    groq_api_key: str = Field(default="")
    groq_api_keys: str = Field(default="")  # Comma-separated multi-key support
    groq_model: str = Field(default="meta-llama/llama-4-scout-17b-16e-instruct")
    groq_models_enabled: list[str] = Field(default=["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant"])
    gemini_api_key: str = Field(default="")
    github_token: str = Field(default="")

    # PostgreSQL checkpoint (v3: replaces SQLite)
    postgres_url: str = Field(default="")

    # Qdrant vector search (v3: new)
    qdrant_url: str = Field(default="")
    qdrant_api_key: str = Field(default="")

    # API & Security
    synapse_admin_key: str = Field(default=...)
    api_version: str = Field(default="v1")
    cors_origins: list[str] = Field(default=...)
    x_content_type_options: str = Field(default="nosniff")
    x_frame_options: str = Field(default="SAMEORIGIN")
    x_xss_protection: str = Field(default="1; mode=block")
    referrer_policy: str = Field(default="strict-origin-when-cross-origin")

    # System
    log_level: str = Field(default="INFO")
    default_domain: str = Field(default="ai")

    # Query & Cache
    query_cache_ttl_seconds: int = Field(default=3600)
    max_query_results: int = Field(default=50)
    max_traversal_depth: int = Field(default=3)

    @classmethod
    def from_env(cls) -> "Settings":
        cors_raw = os.getenv("CORS_ORIGINS")
        if not cors_raw:
            raise ValueError("CORS_ORIGINS environment variable is required")
        cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]

        neo4j_uri = os.getenv("NEO4J_URI")
        if not neo4j_uri:
            raise ValueError("NEO4J_URI environment variable is required")

        synapse_admin_key = os.getenv("SYNAPSE_ADMIN_KEY")
        if not synapse_admin_key:
            raise ValueError("SYNAPSE_ADMIN_KEY environment variable is required")

        groq_models_raw = os.getenv("GROQ_MODELS_ENABLED", "")
        groq_models_enabled = (
            [m.strip() for m in groq_models_raw.split(",") if m.strip()]
            if groq_models_raw
            else ["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant"]
        )

        return cls(
            neo4j_uri=neo4j_uri,
            neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "password"),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            groq_api_keys=os.getenv("GROQ_API_KEYS", ""),
            groq_model=os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            postgres_url=os.getenv("POSTGRES_URL", ""),
            qdrant_url=os.getenv("QDRANT_URL", ""),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            synapse_admin_key=synapse_admin_key,
            api_version=os.getenv("API_VERSION", "v1"),
            cors_origins=cors_origins,
            x_content_type_options=os.getenv("X_CONTENT_TYPE_OPTIONS", "nosniff"),
            x_frame_options=os.getenv("X_FRAME_OPTIONS", "SAMEORIGIN"),
            x_xss_protection=os.getenv("X_XSS_PROTECTION", "1; mode=block"),
            referrer_policy=os.getenv("REFERRER_POLICY", "strict-origin-when-cross-origin"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            default_domain=os.getenv("DEFAULT_DOMAIN", "ai"),
            query_cache_ttl_seconds=int(os.getenv("QUERY_CACHE_TTL_SECONDS", "3600")),
            max_query_results=int(os.getenv("MAX_QUERY_RESULTS", "50")),
            max_traversal_depth=int(os.getenv("MAX_TRAVERSAL_DEPTH", "3")),
            groq_models_enabled=groq_models_enabled,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()  # no-op if already loaded; safe to call multiple times
    return Settings.from_env()
