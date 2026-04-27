from __future__ import annotations

import pytest

from app.config import Settings


def test_local_cors_defaults_allow_vite_dev_server() -> None:
    settings = Settings(APP_ENV="local", BACKEND_CORS_ORIGINS="")

    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_production_requires_explicit_safe_security_config() -> None:
    settings = Settings(
        APP_ENV="production",
        BACKEND_CORS_ORIGINS="*",
        OPENAI_API_KEY="",
        SUPABASE_URL="",
    )

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate_security_config()

    message = str(exc_info.value)
    assert "Wildcard CORS origins are not allowed" in message
    assert "SUPABASE_URL is required" in message
    assert "OPENAI_API_KEY is required" in message
    assert "default development database credentials" in message


def test_production_accepts_explicit_security_config() -> None:
    settings = Settings(
        APP_ENV="production",
        BACKEND_CORS_ORIGINS="https://app.example.com",
        DATABASE_URL="postgresql+psycopg://lumen:strong-password@postgres:5432/lumen",
        OPENAI_API_KEY="sk-test",
        SUPABASE_URL="https://project.supabase.co",
    )

    settings.validate_security_config()
    assert settings.cors_origins == ["https://app.example.com"]
