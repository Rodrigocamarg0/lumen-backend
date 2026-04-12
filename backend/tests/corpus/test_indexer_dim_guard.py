from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.corpus.indexer import KardecIndex

try:
    import faiss
except ImportError:  # pragma: no cover
    faiss = None


@unittest.skipIf(faiss is None, "faiss is not installed")
class KardecIndexDimGuardTests(unittest.TestCase):
    def test_search_raises_clear_error_on_dimension_mismatch(self) -> None:
        index = KardecIndex(dim=384)
        index.embedding_model = "legacy-model"
        index._faiss_index = faiss.IndexFlatIP(384)
        index._chunks = [{"id": "a", "texto": "x"}]
        index._faiss_index.add(np.zeros((1, 384), dtype=np.float32))

        with self.assertRaisesRegex(ValueError, "does not match index dim 384"):
            index.search(np.zeros((1, 1536), dtype=np.float32), top_k=1)


if __name__ == "__main__":
    unittest.main()
