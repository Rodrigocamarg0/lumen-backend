from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import state
from app.api.routes import search
from app.auth import dependencies
from app.auth.dependencies import require_current_user
from app.auth.models import AuthenticatedUser
from app.auth.verifier import AuthVerificationError
from app.config import Settings
from app.db.session import get_db_session
from app.security import add_security_middleware


class _FakeIndex:
    size = 1


class _FakeRag:
    index = _FakeIndex()

    def retrieve(self, query: str, top_k: int, min_score: float):
        return (
            [
                {
                    "id": "lde-1",
                    "obra": "O Livro dos Espiritos",
                    "parte": "Parte primeira",
                    "capitulo": "Capitulo I",
                    "questao": 1,
                    "score": 0.92,
                    "texto": "Texto completo que nao deve ser retornado no campo texto.",
                }
            ],
            12,
        )


def _authenticated_user() -> AuthenticatedUser:
    return AuthenticatedUser(id="user-1", email="user@example.com")


def _db_session():
    yield None


def _search_test_app() -> FastAPI:
    app = FastAPI()
    add_security_middleware(app, Settings(APP_ENV="test"))
    app.include_router(search.router, prefix="/api")
    return app


def test_search_requires_bearer_token() -> None:
    app = _search_test_app()
    app.dependency_overrides[get_db_session] = _db_session
    client = TestClient(app)

    response = client.post("/api/search", json={"query": "alma", "persona_id": "kardec"})

    assert response.status_code == 401


def test_search_rejects_invalid_token(monkeypatch) -> None:
    app = _search_test_app()
    app.dependency_overrides[get_db_session] = _db_session
    monkeypatch.setattr(
        dependencies,
        "verify_supabase_token",
        lambda token: (_ for _ in ()).throw(AuthVerificationError("Invalid token")),
    )
    client = TestClient(app)

    response = client.post(
        "/api/search",
        json={"query": "alma", "persona_id": "kardec"},
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401


def test_search_returns_excerpt_without_full_text(monkeypatch) -> None:
    app = _search_test_app()
    app.dependency_overrides[require_current_user] = _authenticated_user
    monkeypatch.setattr(state, "rag", _FakeRag())
    monkeypatch.setattr(search, "list_persona_ids", lambda: ["kardec"])
    client = TestClient(app)

    response = client.post(
        "/api/search",
        json={"query": "alma", "persona_id": "kardec"},
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["excerpt"] == "Texto completo que nao deve ser retornado no campo texto."
    assert result["texto"] == ""
