"""Centralised application settings using Pydantic BaseSettings.

All configuration is read from environment variables (or .env file).
Replace ALL os.getenv() calls with `from config.settings import settings`
and then `settings.<field>`.

Azure deployment: set env vars in Container Apps → Configuration panel.
SQLite → PostgreSQL migration: change DATABASE_URL only (no code change).

Secret loading order:
  1. .env file is pre-loaded via python-dotenv (local dev / Docker)
  2. Azure Key Vault overrides specific secrets if AZURE_KEYVAULT_URL is set
  3. pydantic-settings reads the final env state into the Settings object
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = structlog.get_logger()

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

# Step 1 — pre-load .env so AZURE_KEYVAULT_URL is readable before Settings()
load_dotenv(str(_ENV_FILE), override=False)


def _load_keyvault_secrets() -> None:
    """Pull secrets from Azure Key Vault into os.environ before Settings() loads.

    Only runs when AZURE_KEYVAULT_URL is set (production / staging).
    Falls back silently to .env values for any secret not in the vault.
    Safe to call on local dev where AZURE_KEYVAULT_URL is empty.
    """
    vault_url = (os.getenv("AZURE_KEYVAULT_URL") or "").strip()
    if not vault_url:
        return  # local dev — .env is enough

    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

        # Key Vault name → env var name mapping
        secret_map: dict[str, str] = {
            "GROQ-API-KEY":                     "GROQ_API_KEY",
            "GROQ-API-KEY-2":                   "GROQ_API_KEY_2",
            "GROQ-API-KEY-3":                   "GROQ_API_KEY_3",
            "OLLAMA-API-KEY":                   "OLLAMA_API_KEY",
            "CODARA-JWT-SECRET":                "CODARA_JWT_SECRET",
            "GITHUB-CLIENT-SECRET":             "GITHUB_CLIENT_SECRET",
            "AZURE-STORAGE-CONNECTION-STRING":  "AZURE_STORAGE_CONNECTION_STRING",
            # Add more as you store them in the vault:
            # "AZURE-OPENAI-API-KEY":           "AZURE_OPENAI_API_KEY",
            # "AZURE-OPENAI-ENDPOINT":          "AZURE_OPENAI_ENDPOINT",
            # "GEMINI-API-KEY":                 "GEMINI_API_KEY",
        }

        loaded, failed = 0, 0
        for kv_name, env_name in secret_map.items():
            try:
                secret = client.get_secret(kv_name)
                os.environ[env_name] = secret.value
                loaded += 1
            except Exception as exc:
                # Secret not in vault — .env value (if any) stays in place
                failed += 1
                _log.debug("keyvault_secret_missing", name=kv_name, error=str(exc))

        _log.info("keyvault_secrets_loaded", loaded=loaded, skipped=failed)

    except Exception as exc:
        # Non-fatal: vault unreachable → app still starts with .env values
        _log.warning("keyvault_load_failed", error=str(exc))


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

    # ── LLM — Ollama / Nemotron (primary) ────────────────────────────────────
    ollama_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "nemotron-3-super:cloud"

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

    def validate_production_secrets(self) -> None:
        """Fail fast if insecure defaults are used in production."""
        if self.app_env == "production":
            if self.codara_jwt_secret.startswith("codara-dev"):
                raise RuntimeError(
                    "CODARA_JWT_SECRET must be set to a strong secret in production. "
                    "Generate one with: openssl rand -hex 32"
                )

    # ── GitHub OAuth ──────────────────────────────────────────────────────────
    github_client_id: str = ""
    github_client_secret: str = ""

    # ── Azure infra ───────────────────────────────────────────────────────────
    applicationinsights_connection_string: str = ""
    # Blob Storage — set AZURE_STORAGE_CONNECTION_STRING to activate
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "codara-uploads"
    # Queue Storage — set AZURE_QUEUE_NAME to override default
    azure_queue_name: str = "codara-pipeline-jobs"

    # ── Feature flags ─────────────────────────────────────────────────────────
    enable_z3_verification: bool = True
    llm_provider: str = "azure"           # legacy: azure | groq

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Override via env: CORS_ORIGINS=https://app.codara.dev,http://localhost:5173
    # pydantic-settings parses comma-separated strings into list[str] automatically.
    cors_origins: list[str] = [
        "http://localhost:8080",
        "http://localhost:5173",
        "http://127.0.0.1:8080",
    ]

    # ── Local GGUF model (Tier 0 — optional) ─────────────────────────────────
    local_model_path: str = ""          # path to .gguf file; empty = disabled
    local_model_threads: int = 4        # CPU threads for llama-cpp inference
    local_model_ctx: int = 4096         # context window in tokens

    # ── Azure Key Vault (production secret injection) ─────────────────────────
    azure_keyvault_url: str = ""        # e.g. https://codara-kv.vault.azure.net/

    # ── Misc ──────────────────────────────────────────────────────────────────
    lancedb_path: str = "lancedb_data"
    duckdb_path: str = "data/analytics.duckdb"


# Step 2 — pull secrets from Key Vault into os.environ (no-op locally)
_load_keyvault_secrets()

# Step 3 — pydantic-settings reads the final env state
# Singleton — import and use everywhere:
#   from config.settings import settings
settings = Settings()
