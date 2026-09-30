"""Configuration settings for IP-SAKTI Sahayak Backend."""
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    PROJECT_NAME: str = "IP-SAKTI Sahayak"
    PROJECT_DESCRIPTION: str = (
        "Evidence-grounded intellectual property and regulatory intelligence copilot for Ayurveda."
    )
    VERSION: str = "0.2.0"
    APP_ENV: str = "development"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_URL: str = "http://localhost:3000"
    API_URL: str = "http://localhost:8000"

    # API & CORS
    API_PREFIX: str = "/api"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Database (Postgres + pgvector)
    DATABASE_URL: str = "postgresql+psycopg://ipsakti:ipsakti@localhost:5433/ipsakti"
    VECTOR_DATABASE_URL: str = ""  # same DB by default (pgvector)
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # Auth
    JWT_SECRET: str = "dev-only-change-me"
    SESSION_SECRET: str = "dev-only-change-me"
    ACCESS_TOKEN_TTL_MINUTES: int = 60 * 12

    # LLM Provider: ollama | gemini | groq | grok | openai | deepseek | mock
    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_MODEL_NAME: str = ""  # legacy alias of LLM_MODEL
    LLM_BASE_URL: str = ""
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 1200
    LLM_TIMEOUT_SECONDS: int = 120
    # Price assumptions (USD per 1M tokens) used only for the cost estimate shown in admin.
    LLM_PRICE_INPUT_PER_M: float = 0.27
    LLM_PRICE_OUTPUT_PER_M: float = 1.10

    # Embeddings: openai | hashing | bge_m3 | mock
    EMBEDDING_PROVIDER: str = "hashing"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_DIMENSION: int = 1024

    # Retrieval
    RETRIEVAL_TOP_K: int = 6
    RETRIEVAL_CANDIDATES: int = 24
    MIN_EVIDENCE_SCORE: float = 0.18

    # Storage / external sources
    STORAGE_PROVIDER: str = "local"
    STORAGE_BUCKET: str = str(REPO_ROOT / "data" / "uploads")
    MAX_UPLOAD_MB: int = 10
    PATENT_API_URL: str = ""
    PUBMED_API_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    REDIS_URL: str = ""

    # Rate limits (requests per minute per user)
    RATE_LIMIT_CHAT: int = 20
    RATE_LIMIT_SEARCH: int = 60
    RATE_LIMIT_INGEST: int = 10
    RATE_LIMIT_REPORT: int = 10

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def llm_model(self) -> str:
        if self.LLM_MODEL:
            return self.LLM_MODEL
        if self.LLM_MODEL_NAME:
            return self.LLM_MODEL_NAME
        return {"deepseek": "deepseek-chat", "grok": "grok-3-mini", "gemini": "gemini-2.5-flash",
                "groq": "llama-3.3-70b-versatile", "ollama": "llama3.2"}.get(self.LLM_PROVIDER.lower(), "gpt-4o-mini")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


settings = Settings()


def validate_settings() -> List[str]:
    """Return human-readable warnings for missing/unsafe configuration."""
    warnings = []
    for k, v in settings.model_dump().items():
        if isinstance(v, str) and v.lstrip().startswith("#"):
            warnings.append(f"{k} looks like a comment ('{v[:30]}…'). Put .env comments on their own line.")
    if settings.JWT_SECRET.startswith("dev-only"):
        if settings.is_production:
            raise RuntimeError("JWT_SECRET must be set in production (see .env.example).")
        warnings.append("JWT_SECRET is using the development default.")
    if settings.LLM_PROVIDER in ("openai", "deepseek", "grok", "gemini", "groq") and not settings.LLM_API_KEY:
        warnings.append(
            f"LLM_PROVIDER={settings.LLM_PROVIDER} but LLM_API_KEY is empty; falling back to extractive mock mode."
        )
    return warnings
