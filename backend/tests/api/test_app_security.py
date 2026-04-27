from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.security import add_security_middleware


def _security_test_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    add_security_middleware(app, settings)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_local_cors_allows_localhost_origin() -> None:
    app = _security_test_app(Settings(APP_ENV="test"))
    client = TestClient(app)

    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_production_cors_rejects_unknown_origin() -> None:
    app = _security_test_app(
        Settings(
            APP_ENV="production",
            BACKEND_CORS_ORIGINS="https://app.example.com",
            DATABASE_URL="postgresql+psycopg://lumen:strong-password@postgres:5432/lumen",
            OPENAI_API_KEY="sk-test",
            SUPABASE_URL="https://project.supabase.co",
        )
    )
    client = TestClient(app)

    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_production_responses_include_security_headers() -> None:
    app = _security_test_app(
        Settings(
            APP_ENV="production",
            BACKEND_CORS_ORIGINS="https://app.example.com",
            DATABASE_URL="postgresql+psycopg://lumen:strong-password@postgres:5432/lumen",
            OPENAI_API_KEY="sk-test",
            SUPABASE_URL="https://project.supabase.co",
        )
    )
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-trace-id"]
