"""
Text embedding using the OpenAI Embeddings API (text-embedding-3-small).

Embeddings are returned unit-normalised (L2-norm == 1) by the API, so
inner-product (dot product) equals cosine similarity — matching the FAISS
IndexFlatIP used by the indexer.

Disk cache
----------
Each embedding is stored under `cache_dir` as
    {sha256(model + "|" + text)[:2] / sha256...}.npy

On a crash and re-run, all previously embedded texts are served from disk
without any API call, so you only pay for the batches that haven't finished.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import re

import numpy as np

logger = logging.getLogger("embedder")

# Known output dimensions — avoids a probe API call for common models.
_OPENAI_DIM: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

_DEFAULT_BATCH = 100  # well under the 2048-input API limit
_API_MAX_TOKENS = 8192
_TOKEN_MARGIN = 256
_SAFE_MAX_TOKENS = _API_MAX_TOKENS - _TOKEN_MARGIN
_MIN_RETRY_TOKENS = 512
_TOKEN_LIMIT_ERROR = re.compile(r"maximum input length is (\d+) tokens", re.IGNORECASE)
_BAD_INPUT_INDEX = re.compile(r"input\[(\d+)\]")


def _get_encoding(model_name: str):
    import tiktoken  # type: ignore[import]

    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


class Embedder:
    """
    Wraps the OpenAI Embeddings API and returns unit-normalised float32
    numpy arrays, with a transparent disk cache to avoid re-embedding.

    Args:
        model_name: OpenAI embedding model ID.
            Default: 'text-embedding-3-small'  (dim=1536)
        cache_dir:  Directory for the embedding cache.
            Default: 'data/embeddings_cache'
            Pass None to disable caching (e.g. for query-time embeddings).

    The OPENAI_API_KEY environment variable (or .env file) must be set.
    """

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        cache_dir: Path | str | None = Path("data/embeddings_cache"),
    ):
        self.model_name = model_name
        self._dim: int | None = _OPENAI_DIM.get(model_name)
        self._client = None
        self._encoding = None
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        if self._cache_dir is not None:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI  # type: ignore[import]

            self._client = OpenAI()  # reads OPENAI_API_KEY from env
        return self._client

    @property
    def dim(self) -> int:
        if self._dim is None:
            sample = self._call_api(["probe"])
            self._dim = int(sample.shape[1])
        return self._dim

    @property
    def encoding(self):
        if self._encoding is None:
            self._encoding = _get_encoding(self.model_name)
        return self._encoding

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_name}|{text}".encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        assert self._cache_dir is not None
        shard = self._cache_dir / key[:2]
        shard.mkdir(exist_ok=True)
        return shard / f"{key}.npy"

    def _load_cached(self, key: str) -> np.ndarray | None:
        if self._cache_dir is None:
            return None
        p = self._cache_path(key)
        if p.exists():
            return np.load(str(p))
        return None

    def _save_cached(self, key: str, vec: np.ndarray) -> None:
        if self._cache_dir is None:
            return
        np.save(str(self._cache_path(key)), vec)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(self, texts: list[str] | str, batch_size: int = _DEFAULT_BATCH) -> np.ndarray:
        """
        Encode texts and return unit-normalised float32 embeddings.

        Shape: (len(texts), dim) — or (1, dim) when a single string is given.

        Texts already in the disk cache are served without any API call.
        """
        if isinstance(texts, str):
            texts = [texts]

        keys = [self._cache_key(t) for t in texts]

        # Split into cached / uncached
        cached_vecs: dict[str, np.ndarray] = {}
        uncached_indices: list[int] = []
        for i, key in enumerate(keys):
            vec = self._load_cached(key)
            if vec is not None:
                cached_vecs[key] = vec
            else:
                uncached_indices.append(i)

        if uncached_indices:
            n_total = len(texts)
            n_cached = n_total - len(uncached_indices)
            logger.info(
                f"Encoding {len(uncached_indices)} texts via API "
                f"({n_cached}/{n_total} served from cache) …"
            )
            uncached_texts = [texts[i] for i in uncached_indices]
            batches = [
                uncached_texts[i : i + batch_size]
                for i in range(0, len(uncached_texts), batch_size)
            ]
            batch_offset = 0
            for b_idx, batch in enumerate(batches):
                logger.debug(f"API batch {b_idx + 1}/{len(batches)}: {len(batch)} texts")
                vecs = self._call_api(batch)
                for j, vec in enumerate(vecs):
                    orig_idx = uncached_indices[batch_offset + j]
                    self._save_cached(keys[orig_idx], vec)
                    cached_vecs[keys[orig_idx]] = vec
                batch_offset += len(batch)
        else:
            logger.info(f"All {len(texts)} embeddings served from cache — no API call")

        return np.vstack([cached_vecs[k] for k in keys])

    def encode_query(self, query: str) -> np.ndarray:
        """
        Encode a single query string. Returns shape (1, dim).
        Cache is bypassed for queries (called at request time, not ingestion).
        """
        original_cache = self._cache_dir
        self._cache_dir = None
        try:
            return self.encode([query])
        finally:
            self._cache_dir = original_cache

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _token_count(self, text: str) -> int:
        return len(self.encoding.encode(text))

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated = self.encoding.decode(tokens[:max_tokens])
        while len(self.encoding.encode(truncated)) > max_tokens:
            max_tokens -= 1
            if max_tokens <= 0:
                return ""
            truncated = self.encoding.decode(tokens[:max_tokens])
        return truncated

    def _prepare_text(self, text: str, max_tokens: int = _SAFE_MAX_TOKENS) -> str:
        prepared = self._truncate_to_tokens(text, max_tokens=max_tokens)
        if prepared != text:
            logger.warning(
                f"Text truncated from {self._token_count(text)} to "
                f"{self._token_count(prepared)} tokens"
            )
        return prepared

    def _embed_single_with_backoff(self, text: str) -> np.ndarray:
        from openai import BadRequestError  # type: ignore[import]

        max_tokens = _SAFE_MAX_TOKENS
        while True:
            prepared = self._prepare_text(text, max_tokens=max_tokens)
            try:
                response = self.client.embeddings.create(model=self.model_name, input=[prepared])
                return np.array(response.data[0].embedding, dtype=np.float32)
            except BadRequestError as exc:
                message = str(exc)
                if "maximum input length" not in message:
                    raise
                if max_tokens <= _MIN_RETRY_TOKENS:
                    raise
                max_tokens = max(_MIN_RETRY_TOKENS, int(max_tokens * 0.85))
                logger.warning(
                    f"Retrying oversized embedding input with stricter limit ({max_tokens} tokens)"
                )

    def _call_api(self, texts: list[str]) -> np.ndarray:
        from openai import BadRequestError  # type: ignore[import]

        prepared = [self._prepare_text(t) for t in texts]
        try:
            response = self.client.embeddings.create(model=self.model_name, input=prepared)
        except BadRequestError as exc:
            message = str(exc)
            if "maximum input length" not in message:
                raise

            limit_match = _TOKEN_LIMIT_ERROR.search(message)
            idx_match = _BAD_INPUT_INDEX.search(message)
            limit = limit_match.group(1) if limit_match else str(_API_MAX_TOKENS)
            bad_index = idx_match.group(1) if idx_match else "unknown"
            logger.warning(
                f"Batch embedding request rejected for input[{bad_index}] over {limit} tokens; "
                "falling back to per-item retries"
            )
            repaired = [self._embed_single_with_backoff(text) for text in texts]
            return np.vstack(repaired)

        ordered = sorted(response.data, key=lambda item: item.index)
        return np.array([item.embedding for item in ordered], dtype=np.float32)
