from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.corpus.indexer import KardecIndex

try:
    import faiss
except ImportError:  # pragma: no cover
    faiss = None


class FakeEmbedder:
    model_name = "text-embedding-3-small"

    def __init__(self, vectors: np.ndarray) -> None:
        self._vectors = vectors.astype(np.float32)

    def encode(self, texts: list[str], batch_size: int = 256) -> np.ndarray:
        return self._vectors[: len(texts)]


@unittest.skipIf(faiss is None, "faiss is not installed")
class KardecIndexTurboQuantTests(unittest.TestCase):
    def test_save_load_and_search_quantized_index(self) -> None:
        vectors = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )
        chunks = [
            {"id": "a", "texto": "primeiro", "obra": "Livro A"},
            {"id": "b", "texto": "segundo", "obra": "Livro B"},
            {"id": "c", "texto": "terceiro", "obra": "Livro C"},
        ]

        index = KardecIndex()
        index.build(
            FakeEmbedder(vectors),
            chunks,
            quantize=True,
            quantization_bits=3,
            quantization_seed=17,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            index.save(target, name="kardec")
            loaded = KardecIndex.load(target, name="kardec")

            results = loaded.search(np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32), top_k=1)

            self.assertEqual(loaded.storage_format, "turboquant_mse")
            self.assertIsNotNone(loaded.quantized)
            self.assertIsNotNone(loaded.quantizer)
            self.assertEqual(results[0]["id"], "a")


if __name__ == "__main__":
    unittest.main()
