from __future__ import annotations

import numpy as np

from app.persona.rag import RAGOrchestrator, question_similarity, rerank_question_matches

LDE_Q258_PROMPT = (
    "No estado errante, antes de nova existência corpórea, o Espírito tem consciência "
    "e previsão do que lhe vai acontecer durante a vida?"
)


def test_question_similarity_matches_lde_258_paraphrase() -> None:
    chunk = {
        "id": "lde-q0258",
        "questao": 258,
        "texto": (
            "Quando na erraticidade, antes de começar nova existência corporal, "
            "tem o Espírito consciência e previsão do que lhe sucederá no curso "
            "da vida terrena?\n\n"
            '"Ele próprio escolhe o gênero de provas por que há de passar."'
        ),
    }

    assert question_similarity(LDE_Q258_PROMPT, chunk) >= 0.35


def test_question_similarity_ignores_non_question_chunks() -> None:
    chunk = {
        "id": "gen-c11-p042",
        "questao": None,
        "texto": (
            "21. Mas, ao mesmo tempo que o Espírito recobra a consciência de si mesmo, "
            "perde a lembrança do seu passado."
        ),
    }

    assert question_similarity(LDE_Q258_PROMPT, chunk) == 0.0


def test_rerank_question_matches_promotes_lde_258() -> None:
    chunks = [
        {
            "id": "gen-c11-p040",
            "questao": None,
            "score": 0.686312,
            "texto": "O Espiritismo dá a conhecer os fenômenos que acompanham a separação.",
        },
        {
            "id": "lde-q0258",
            "questao": 258,
            "score": 0.620913,
            "texto": (
                "Quando na erraticidade, antes de começar nova existência corporal, "
                "tem o Espírito consciência e previsão do que lhe sucederá no curso "
                "da vida terrena?\n\n"
                '"Ele próprio escolhe o gênero de provas por que há de passar."'
            ),
        },
    ]

    results = rerank_question_matches(LDE_Q258_PROMPT, chunks, top_k=2)

    assert results[0]["id"] == "lde-q0258"
    assert results[0]["score"] > results[0]["semantic_score"]
    assert results[0]["question_match_score"] > results[1]["question_match_score"]


class _FakeEmbedder:
    def encode_query(self, query: str) -> np.ndarray:
        return np.array([[1.0, 0.0]], dtype=np.float32)


class _FakeIndex:
    def __init__(self) -> None:
        self.requested_top_k: int | None = None

    def search(self, query_vec: np.ndarray, top_k: int, min_score: float) -> list[dict]:
        self.requested_top_k = top_k
        return [
            {
                "id": "gen-c11-p040",
                "questao": None,
                "score": 0.686312,
                "texto": "O Espiritismo dá a conhecer os fenômenos que acompanham a separação.",
            },
            {
                "id": "lde-q0258",
                "questao": 258,
                "score": 0.620913,
                "texto": (
                    "Quando na erraticidade, antes de começar nova existência corporal, "
                    "tem o Espírito consciência e previsão do que lhe sucederá no curso "
                    "da vida terrena?\n\n"
                    '"Ele próprio escolhe o gênero de provas por que há de passar."'
                ),
            },
        ]


def test_retrieve_overfetches_and_reranks_question_matches() -> None:
    index = _FakeIndex()
    rag = RAGOrchestrator(index=index, embedder=_FakeEmbedder())

    chunks, _latency_ms = rag.retrieve(LDE_Q258_PROMPT, top_k=1)

    assert index.requested_top_k is not None
    assert index.requested_top_k > 1
    assert chunks[0]["id"] == "lde-q0258"
