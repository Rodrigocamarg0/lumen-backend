from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.cache import TurboQuantMSE


class TurboQuantMSETests(unittest.TestCase):
    def test_quantize_and_dequantize_round_trip(self) -> None:
        rng = np.random.default_rng(7)
        vectors = rng.standard_normal((8, 32), dtype=np.float32)

        quantizer = TurboQuantMSE(dim=32, bits=3, seed=11)
        quantized = quantizer.quantize(vectors)
        restored = quantizer.dequantize(quantized)

        self.assertEqual(quantized.shape, (8, 32))
        self.assertEqual(quantized.storage_bits, 3)
        self.assertEqual(restored.shape, vectors.shape)

        original_norms = np.linalg.norm(vectors, axis=1)
        restored_norms = np.linalg.norm(restored, axis=1)
        self.assertTrue(np.allclose(original_norms, restored_norms, atol=1e-3))

        cosine = np.sum(vectors * restored, axis=1) / (
            np.linalg.norm(vectors, axis=1) * np.linalg.norm(restored, axis=1)
        )
        self.assertGreater(float(np.mean(cosine)), 0.75)

    def test_fractional_bits_round_up_for_storage(self) -> None:
        quantizer = TurboQuantMSE(dim=16, bits=3.5, seed=5)
        self.assertEqual(quantizer.storage_bits, 4)


if __name__ == "__main__":
    unittest.main()
