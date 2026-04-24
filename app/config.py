"""Configuration for the Governor Chatbot Service."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service
    port: int = int(os.getenv("PORT", "8000"))
    host: str = os.getenv("HOST", "0.0.0.0")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # CORS
    cors_origins: list[str] = ["*"]  # TODO: restrict to dapp.truesight.me in production

    # Security
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 30
    nonce_ttl_seconds: int = 300  # 5 minutes
    timestamp_skew_seconds: int = 120  # 2 minutes

    # Kimi / LLM
    kimi_api_key: str | None = os.getenv("KIMI_API_KEY")
    kimi_base_url: str = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
    kimi_model: str = os.getenv("KIMI_MODEL", "kimi-latest")
    kimi_max_tokens: int = int(os.getenv("KIMI_MAX_TOKENS", "4096"))
    kimi_temperature: float = float(os.getenv("KIMI_TEMPERATURE", "0.3"))

    # Context
    context_repos_dir: Path = Path(os.getenv("CONTEXT_REPOS_DIR", "/opt/governor_chatbot/context"))
    agentic_context_repo: str = os.getenv(
        "AGENTIC_CONTEXT_REPO", "https://github.com/TrueSightDAO/agentic_ai_context.git"
    )

    # Governor registry
    governor_registry_source: str = os.getenv("GOVERNOR_REGISTRY_SOURCE", "static")  # "edgar" | "sheet" | "static"
    static_governors_json: Path | None = Path(os.getenv("STATIC_GOVERNORS_JSON")) if os.getenv("STATIC_GOVERNORS_JSON") else None

    # Edgar (Phase 2)
    edgar_api_url: str = os.getenv("EDGAR_API_URL", "https://edgar.truesight.me")
    edgar_api_token: str | None = os.getenv("EDGAR_API_TOKEN")

    # GitHub (Phase 2–3)
    github_pat: str | None = os.getenv("GITHUB_PAT")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
