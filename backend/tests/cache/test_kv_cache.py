from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.cache import TurboQuantCache
from app.cache.kv_cache import _unpack_bits


class _ModuleStub:
    num_key_value_groups = 1
    training = False


class TurboQuantCacheTests(unittest.TestCase):
    def test_update_tracks_seq_length_and_metrics(self) -> None:
        cache = TurboQuantCache(bits=3.5, outlier_threshold=10.0, num_hidden_layers=2)
        key_states = torch.randn(1, 2, 3, 8, dtype=torch.float32)
        value_states = torch.randn(1, 2, 3, 8, dtype=torch.float32)

        keys, values = cache.update(key_states, value_states, layer_idx=0)

        self.assertEqual(tuple(keys.shape), (1, 2, 3, 8))
        self.assertEqual(tuple(values.shape), (1, 2, 3, 8))
        self.assertEqual(cache.get_seq_length(0), 3)
        metrics = cache.memory_stats()
        self.assertTrue(metrics["layers_initialized"] >= 1)
        self.assertTrue(metrics["compressed_mb"] >= 0.0)

    def test_update_appends_sequence(self) -> None:
        cache = TurboQuantCache(bits=3.5, outlier_threshold=10.0, num_hidden_layers=1)
        first = torch.randn(1, 1, 2, 8, dtype=torch.float32)
        second = torch.randn(1, 1, 1, 8, dtype=torch.float32)

        cache.update(first, first, layer_idx=0)
        keys, values = cache.update(second, second, layer_idx=0)

        self.assertEqual(tuple(keys.shape), (1, 1, 3, 8))
        self.assertEqual(tuple(values.shape), (1, 1, 3, 8))
        self.assertEqual(cache.get_seq_length(0), 3)

    def test_quantized_attention_matches_dequantized_baseline(self) -> None:
        cache = TurboQuantCache(bits=3.5, outlier_threshold=1000.0, num_hidden_layers=1)
        key_states = torch.randn(1, 1, 4, 8, dtype=torch.float32)
        value_states = torch.randn(1, 1, 4, 8, dtype=torch.float32)
        cache.update(key_states, value_states, layer_idx=0)

        layer = cache.layers[0]
        query = torch.randn(1, 1, 2, 8, dtype=torch.float32)
        module = _ModuleStub()
        module.head_dim = 8

        attn_output, attn_weights = cache.quantized_attention.forward(
            module,
            query,
            layer.k_state,
            layer.v_state,
            layer,
            attention_mask=None,
            scaling=8**-0.5,
            dropout=0.0,
        )

        regular_mask = layer.regular_mask
        rotation = layer._quantizer_rotation(query.device, torch.float32)
        centroids = layer._quantizer_centroids(query.device, torch.float32)
        key_idx = _unpack_bits(
            layer.k_state.packed_indices, layer.k_state.storage_bits, layer.k_state.regular_dim
        )
        value_idx = _unpack_bits(
            layer.v_state.packed_indices, layer.v_state.storage_bits, layer.v_state.regular_dim
        )
        key_reg = (centroids[key_idx] * layer.k_state.norms.unsqueeze(-1)) @ rotation
        value_reg = (centroids[value_idx] * layer.v_state.norms.unsqueeze(-1)) @ rotation

        full_keys = torch.zeros_like(key_states)
        full_values = torch.zeros_like(value_states)
        full_keys[..., regular_mask] = key_reg
        full_values[..., regular_mask] = value_reg

        baseline_scores = torch.matmul(query, full_keys.transpose(2, 3)) * (8**-0.5)
        baseline_weights = torch.softmax(baseline_scores, dim=-1)
        baseline_output = torch.matmul(baseline_weights, full_values).transpose(1, 2).contiguous()

        self.assertTrue(torch.allclose(attn_output, baseline_output, atol=1e-4, rtol=1e-4))
        self.assertTrue(torch.allclose(attn_weights, baseline_weights, atol=1e-4, rtol=1e-4))


if __name__ == "__main__":
    unittest.main()
