"""
FAISS index builder, saver, loader and searcher.

Index type: IndexFlatIP (exact inner-product search).
Since embeddings are L2-normalised, IP == cosine similarity.

Disk layout (under a given directory):
    kardec.index       — FAISS binary
    kardec_meta.jsonl  — one JSON line per chunk (same order as FAISS vectors)
    kardec_info.json   — dim, total vectors, model name, build date
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time

import numpy as np

logger = logging.getLogger("indexer")

_FAISS_EXT = ".index"
_META_EXT = "_meta.jsonl"
_INFO_EXT = "_info.json"


def _require_faiss():
    try:
        import faiss  # type: ignore

        return faiss
    except ImportError as exc:
        raise ImportError(
            "faiss-cpu (or faiss-gpu) is required. Install with: pip install faiss-cpu"
        ) from exc


class KardecIndex:
    """
    Manages a single FAISS inner-product index over all corpus chunks.

    Typical lifecycle:
        idx = KardecIndex(dim=384)
        idx.build(embedder, chunks)
        idx.save(Path("data/kardec/index"), name="kardec")

        # Later (or in the API server):
        idx = KardecIndex.load(Path("data/kardec/index"), name="kardec")
        results = idx.search(query_vec, top_k=5)
    """

    def __init__(self, dim: int | None = None):
        self._faiss_index = None
        self._chunks: list[dict] = []
        self.dim = dim

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, embedder, chunks: list[dict], batch_size: int = 256) -> KardecIndex:
        """
        Embed all chunks and populate the FAISS index.

        Args:
            embedder: An `Embedder` instance.
            chunks:   List of chunk dicts (must have "texto" key).
            batch_size: Embedding batch size.
        """
        faiss = _require_faiss()
        texts = [c["texto"] for c in chunks]
        logger.info(f"Embedding {len(texts)} chunks …")
        t0 = time.perf_counter()
        vectors = embedder.encode(texts, batch_size=batch_size)
        elapsed = time.perf_counter() - t0
        logger.info(f"Embedding done in {elapsed:.1f}s  shape={vectors.shape}")

        dim = vectors.shape[1]
        self.dim = dim
        self._faiss_index = faiss.IndexFlatIP(dim)
        self._faiss_index.add(vectors)
        self._chunks = list(chunks)
        logger.info(f"FAISS index built: {self._faiss_index.ntotal} vectors, dim={dim}")
        return self

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    def save(self, directory: Path, name: str = "kardec") -> None:
        faiss = _require_faiss()
        directory.mkdir(parents=True, exist_ok=True)

        index_path = directory / f"{name}{_FAISS_EXT}"
        meta_path = directory / f"{name}{_META_EXT}"
        info_path = directory / f"{name}{_INFO_EXT}"

        faiss.write_index(self._faiss_index, str(index_path))
        logger.info(f"FAISS index → {index_path}")

        with open(meta_path, "w", encoding="utf-8") as f:
            for chunk in self._chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
        logger.info(f"Metadata → {meta_path}")

        import datetime

        assert self._faiss_index is not None
        info = {
            "name": name,
            "dim": self.dim,
            "total_vectors": self._faiss_index.ntotal,
            "build_date": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
        logger.info(f"Info → {info_path}")

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, directory: Path, name: str = "kardec") -> KardecIndex:
        faiss = _require_faiss()
        index_path = directory / f"{name}{_FAISS_EXT}"
        meta_path = directory / f"{name}{_META_EXT}"

        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {index_path}")
        if not meta_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {meta_path}")

        logger.info(f"Loading FAISS index from {index_path} …")
        faiss_index = faiss.read_index(str(index_path))

        chunks: list[dict] = []
        with open(meta_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))

        instance = cls(dim=faiss_index.d)
        instance._faiss_index = faiss_index
        instance._chunks = chunks
        logger.info(f"Index loaded: {faiss_index.ntotal} vectors, {len(chunks)} chunks")
        return instance

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict]:
        """
        Retrieve top-k chunks by inner-product similarity.

        Args:
            query_vec:  Shape (1, dim) or (dim,). L2-normalised.
            top_k:      Number of results to return.
            min_score:  Minimum score threshold (0.0 = no threshold).

        Returns:
            List of chunk dicts enriched with a "score" float key,
            ordered highest-score first.
        """
        if self._faiss_index is None:
            raise RuntimeError("Index not built or loaded")

        vec = np.atleast_2d(query_vec).astype(np.float32)
        t0 = time.perf_counter()
        scores, indices = self._faiss_index.search(vec, top_k)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.debug(f"FAISS search: {latency_ms}ms, top score={scores[0][0]:.4f}")

        results = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if idx < 0:
                continue
            if float(score) < min_score:
                continue
            chunk = dict(self._chunks[idx])
            chunk["score"] = round(float(score), 6)
            results.append(chunk)

        return results

    @property
    def size(self) -> int:
        return len(self._chunks)

    def is_ready(self) -> bool:
        return self._faiss_index is not None and len(self._chunks) > 0


# ---------------------------------------------------------------------------
# Convenience: build index from JSONL chunk files
# ---------------------------------------------------------------------------


def build_index_from_chunks(
    chunks_dir: Path,
    index_dir: Path,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    name: str = "kardec",
) -> KardecIndex:
    """
    Load all *_chunks.jsonl files from `chunks_dir`, embed them, save to
    `index_dir`, and return the built index.
    """
    from app.corpus.embedder import Embedder  # type: ignore[import]

    all_chunks: list[dict] = []
    for jsonl in sorted(chunks_dir.glob("*_chunks.jsonl")):
        with open(jsonl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_chunks.append(json.loads(line))
        logger.info(f"Loaded {jsonl.name}: running total {len(all_chunks)} chunks")

    if not all_chunks:
        raise ValueError(f"No chunks found in {chunks_dir}")

    embedder = Embedder(model_name=model_name)
    idx = KardecIndex()
    idx.build(embedder, all_chunks)
    idx.save(index_dir, name=name)
    return idx


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    ap = argparse.ArgumentParser(description="Build FAISS index from chunk JSONL files")
    ap.add_argument(
        "--chunks", default="data/kardec/chunks", help="Directory with *_chunks.jsonl files"
    )
    ap.add_argument("--output", default="data/kardec/index", help="Directory for index output")
    ap.add_argument(
        "--model", default="sentence-transformers/all-MiniLM-L6-v2", help="Embedding model"
    )
    ap.add_argument("--name", default="kardec", help="Index name prefix")
    args = ap.parse_args()

    idx = build_index_from_chunks(
        chunks_dir=Path(args.chunks),
        index_dir=Path(args.output),
        model_name=args.model,
        name=args.name,
    )
    print(f"Index built: {idx.size} vectors → {args.output}/{args.name}.index")
    sys.exit(0)
