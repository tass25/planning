"""Centralised application settings using Pydantic BaseSettings.

All configuration is read from environment variables (or .env file).
Replace ALL os.getenv() calls with `from config.settings import settings`
and then `settings.<field>`.

Azure deployment: set env vars in Container Apps → Configuration panel.
SQLite → PostgreSQL migration: change DATABASE_URL only (no code change).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Codara application settings.

    All fields map 1-to-1 with environment variable names (case-insensitive).
    Fields without a default are required at startup.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = "development"          # development | staging | production
    app_version: str = "3.1.0"

    # ── Database ──────────────────────────────────────────────────────────────
    # Override with postgresql+asyncpg://... for Azure SQL
    sqlite_path: str = ""                 # resolved in validator below
    database_url: str = ""                # resolved in validator below

    @field_validator("sqlite_path", mode="before")
    @classmethod
    def _default_sqlite_path(cls, v: str) -> str:
        if v:
            return v
        return str(
            Path(__file__).resolve().parent.parent / "data" / "codara_api.db"
        )

    @field_validator("database_url", mode="before")
    @classmethod
    def _default_database_url(cls, v: str, info) -> str:
        if v:
            return v
        # Derive from sqlite_path if not explicitly set
        return ""  # resolved lazily in get_database_url()

    def get_database_url(self) -> str:
        """Return a SQLAlchemy-compatible database URL."""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.sqlite_path}"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── LLM — Ollama (primary) ────────────────────────────────────────────────
    ollama_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "minimax-m2.7:cloud"

    # ── LLM — Azure OpenAI (fallback 1) ──────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment_mini: str = "gpt-4o-mini"
    azure_openai_deployment_full: str = "gpt-4o"

    # ── LLM — Groq (fallback 2 + cross-verifier) ─────────────────────────────
    groq_api_key: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # ── LLM — Gemini (oracle / judge) ────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ── LLM — Cerebras (Best-of-N) ───────────────────────────────────────────
    cerebras_api_key: str = ""
    cerebras_model: str = "llama3.1-70b"

    # ── JWT ───────────────────────────────────────────────────────────────────
    codara_jwt_secret: str = "codara-dev-secret-change-in-production"

    # ── GitHub OAuth ──────────────────────────────────────────────────────────
    github_client_id: str = ""
    github_client_secret: str = ""

    # ── Azure infra ───────────────────────────────────────────────────────────
    applicationinsights_connection_string: str = ""
    azure_storage_account_url: str = ""   # for file uploads → Blob Storage (future)

    # ── Feature flags ─────────────────────────────────────────────────────────
    enable_z3_verification: bool = True
    use_hyper_raptor: bool = False
    llm_provider: str = "azure"           # legacy: azure | groq

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list in env: CORS_ORIGINS=https://app.codara.dev,http://localhost:5173
    cors_origins: list[str] = [
        "http://localhost:8080",
        "http://localhost:5173",
        "http://127.0.0.1:8080",
    ]

    # ── Misc ──────────────────────────────────────────────────────────────────
    lancedb_path: str = "lancedb_data"
    duckdb_path: str = "data/analytics.duckdb"


# Singleton — import and use everywhere:
#   from config.settings import settings
settings = Settings()
