"""
Text embedding using sentence-transformers.

Embeddings are L2-normalised so that inner-product (dot product) equals
cosine similarity — which matches the FAISS IndexFlatIP used by the indexer.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger("embedder")

# Lazy import so the module can be imported without GPU / sentence-transformers
# available in environments that only run the parser.
_model = None
_model_name: str = ""


def _get_model(model_name: str):
    global _model, _model_name
    if _model is None or _model_name != model_name:
        from sentence_transformers import SentenceTransformer  # type: ignore

        logger.info(f"Loading embedding model: {model_name}")
        _model = SentenceTransformer(model_name)
        _model_name = model_name
        logger.info("Embedding model ready")
    return _model


class Embedder:
    """
    Wraps a SentenceTransformer model and always returns L2-normalised
    float32 numpy arrays.

    Args:
        model_name: HuggingFace model ID or local path.
            Default: 'sentence-transformers/all-MiniLM-L6-v2'
            Recommended for multilingual: 'intfloat/multilingual-e5-large'
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._dim: int | None = None

    @property
    def model(self):
        return _get_model(self.model_name)

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = self.model.get_sentence_embedding_dimension()
        return self._dim

    def encode(self, texts: list[str] | str, batch_size: int = 64) -> np.ndarray:
        """
        Encode texts and return L2-normalised float32 embeddings.

        Shape: (len(texts), dim) — or (1, dim) when a single string is given.
        """
        if isinstance(texts, str):
            texts = [texts]

        logger.debug(f"Encoding {len(texts)} texts with batch_size={batch_size}")
        vecs = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,  # L2 norm so IP == cosine
            convert_to_numpy=True,
        )
        return vecs.astype(np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        """
        Encode a single query string. Returns shape (1, dim).
        """
        return self.encode([query])
