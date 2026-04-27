from __future__ import annotations

import os
from typing import Literal

from pydantic_settings import BaseSettings

LOCAL_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
DEFAULT_DATABASE_URL = "postgresql+psycopg://ai:ai@localhost:5532/ai"


class Settings(BaseSettings):
    APP_ENV: Literal["local", "test", "production"] = "local"
    LLM_PROVIDER: str = "openai"
    OPENAI_MODEL: str = "gpt-4.1-nano"
    # Reasoning effort for OpenAI thinking models: low | medium | high | xhigh
    # Leave empty to disable thinking mode.
    OPENAI_REASONING_EFFORT: str = ""

    EMBEDDING_MODEL: str = "text-embedding-3-small"
    ENABLED_PERSONAS: str = "kardec"
    MAX_NEW_TOKENS: int = 512
    BACKEND_CORS_ORIGINS: str = ""
    OPENAI_API_KEY: str = ""
    DATABASE_URL: str = DEFAULT_DATABASE_URL
    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_VERIFY_ISSUER: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        origins = [
            origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()
        ]
        if origins:
            return origins
        if self.APP_ENV in {"local", "test"}:
            return list(LOCAL_CORS_ORIGINS)
        return []

    def validate_security_config(self) -> None:
        if not self.is_production:
            return

        errors: list[str] = []
        origins = self.cors_origins
        if not origins:
            errors.append("BACKEND_CORS_ORIGINS is required in production")
        if "*" in origins:
            errors.append("Wildcard CORS origins are not allowed in production")
        if not self.SUPABASE_URL:
            errors.append("SUPABASE_URL is required in production")
        if not self.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required in production")
        if not self.DATABASE_URL:
            errors.append("DATABASE_URL is required in production")
        if self.DATABASE_URL == DEFAULT_DATABASE_URL or "://ai:ai@" in self.DATABASE_URL:
            errors.append("DATABASE_URL uses the default development database credentials")

        if errors:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


settings = Settings()

# Expose tokens to their respective SDKs automatically
if settings.OPENAI_API_KEY:
    os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)
