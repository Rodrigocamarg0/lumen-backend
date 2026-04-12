"""
TurboQuant KV cache and direct compressed attention.

This module implements the Phase 2 path required by the architecture spec:
  - K/V states are stored in compressed form per layer
  - updates append compressed states directly, without re-materializing history
  - attention scores and value aggregation operate on compressed indices

The implementation is optimized for the current Lumen target:
Gemma attention on the HuggingFace CUDA / CPU backend, using 4-bit storage
(the current `3.5`-bit config rounds up to 4-bit packed nibbles).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MethodType
from typing import Any

import torch
import torch.nn.functional as functional
from transformers.cache_utils import Cache, CacheLayerMixin, DynamicCache

from app.cache.turboquant import TurboQuantMSE


@dataclass(frozen=True)
class QuantizedTensorState:
    packed_indices: torch.Tensor
    norms: torch.Tensor
    regular_dim: int
    storage_bits: int
    requested_bits: float
    outlier_values: torch.Tensor | None


def _detect_outliers(tensor: torch.Tensor, threshold: float) -> torch.Tensor:
    flat = tensor.detach().to(dtype=torch.float32).reshape(-1, tensor.shape[-1])
    if flat.numel() == 0:
        return torch.zeros((tensor.shape[-1],), dtype=torch.bool, device=tensor.device)
    rms = torch.sqrt(torch.mean(flat.square(), dim=0))
    baseline = rms.mean()
    if baseline <= 0:
        return torch.zeros_like(rms, dtype=torch.bool)
    return rms > (baseline * threshold)


def _pack_bits(indices: torch.Tensor, bits: int) -> torch.Tensor:
    """Pack integer indices into bytes. bits must divide 8 evenly (1, 2, 4, or 8)."""
    if 8 % bits != 0:
        raise ValueError(f"bits must divide 8 evenly (1, 2, 4, or 8), got {bits}")
    vpb = 8 // bits  # values per byte
    mask = (1 << bits) - 1
    remainder = indices.shape[-1] % vpb
    if remainder != 0:
        pad = torch.zeros(
            *indices.shape[:-1], vpb - remainder, dtype=indices.dtype, device=indices.device
        )
        indices = torch.cat([indices, pad], dim=-1)
    # Reshape to (..., num_bytes, vpb), apply per-slot shifts, OR into bytes — no Python loop.
    grouped = indices.reshape(*indices.shape[:-1], -1, vpb)
    shifts = torch.arange(vpb, dtype=torch.uint8, device=indices.device) * bits
    packed = ((grouped.to(torch.uint8) & mask) << shifts).sum(dim=-1, dtype=torch.uint8)
    return packed


def _unpack_bits(packed: torch.Tensor, bits: int, dim: int) -> torch.Tensor:
    """Unpack bytes into integer indices."""
    if 8 % bits != 0:
        raise ValueError(f"bits must divide 8 evenly (1, 2, 4, or 8), got {bits}")
    vpb = 8 // bits
    mask = (1 << bits) - 1
    # Vectorized: shift each byte by per-slot amounts, mask, then flatten.
    shifts = torch.arange(vpb, dtype=torch.uint8, device=packed.device) * bits
    expanded = ((packed.unsqueeze(-1) >> shifts) & mask).reshape(*packed.shape[:-1], -1)
    return expanded[..., :dim].to(torch.long)


class TurboQuantCacheLayer(CacheLayerMixin):
    is_sliding = False

    def __init__(self, bits: float, outlier_threshold: float, seed: int):
        super().__init__()
        self.bits = bits
        self.outlier_threshold = outlier_threshold
        self.seed = seed
        self.quantizer: TurboQuantMSE | None = None
        self.dtype: torch.dtype | None = None
        self.device: torch.device | None = None
        self.full_dim = 0
        self.seq_length = 0
        self.regular_mask: torch.Tensor | None = None
        self.outlier_mask: torch.Tensor | None = None
        self.k_state: QuantizedTensorState | None = None
        self.v_state: QuantizedTensorState | None = None
        self.baseline_bytes = 0
        self.compressed_bytes = 0
        self._rotation_cache: dict[tuple[str, torch.dtype], torch.Tensor] = {}
        self._centroids_cache: dict[tuple[str, torch.dtype], torch.Tensor] = {}

    def lazy_initialization(self, key_states: torch.Tensor, value_states: torch.Tensor) -> None:
        self.dtype = key_states.dtype
        self.device = key_states.device
        self.full_dim = int(key_states.shape[-1])
        combined = torch.cat([key_states, value_states], dim=-2)
        self.outlier_mask = _detect_outliers(combined, threshold=self.outlier_threshold)
        self.regular_mask = ~self.outlier_mask
        regular_dim = int(self.regular_mask.sum().item())
        if regular_dim <= 0:
            raise ValueError("TurboQuantCacheLayer requires at least one non-outlier channel")
        self.quantizer = TurboQuantMSE(dim=regular_dim, bits=self.bits, seed=self.seed)
        self.keys = torch.empty((0,), dtype=torch.float32, device=key_states.device)
        self.values = torch.empty((0,), dtype=torch.float32, device=value_states.device)
        self.is_initialized = True

    def _quantizer_rotation(self, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        key = (str(device), dtype)
        if key not in self._rotation_cache:
            assert self.quantizer is not None
            self._rotation_cache[key] = torch.tensor(
                self.quantizer.rotation,
                dtype=dtype,
                device=device,
            )
        return self._rotation_cache[key]

    def _quantizer_centroids(self, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        key = (str(device), dtype)
        if key not in self._centroids_cache:
            assert self.quantizer is not None
            self._centroids_cache[key] = torch.tensor(
                self.quantizer.centroids,
                dtype=dtype,
                device=device,
            )
        return self._centroids_cache[key]

    def _quantize_tensor(self, tensor: torch.Tensor) -> QuantizedTensorState:
        assert self.quantizer is not None
        assert self.regular_mask is not None
        assert self.outlier_mask is not None

        regular = tensor[..., self.regular_mask].to(dtype=torch.float32)
        flat = regular.reshape(-1, regular.shape[-1])
        norms = torch.linalg.vector_norm(flat, dim=-1)
        safe_norms = torch.where(norms > 0, norms, torch.ones_like(norms))
        normalized = flat / safe_norms.unsqueeze(-1)

        rotation = self._quantizer_rotation(flat.device, flat.dtype)
        rotated = normalized @ rotation.T

        boundaries = torch.tensor(
            self.quantizer.boundaries[1:-1],
            dtype=flat.dtype,
            device=flat.device,
        )
        indices = torch.bucketize(rotated.contiguous(), boundaries).to(torch.uint8)
        packed = _pack_bits(indices, self.quantizer.storage_bits).reshape(*tensor.shape[:-1], -1)
        norms = norms.reshape(*tensor.shape[:-1]).to(torch.float32)

        outlier_values = None
        if bool(self.outlier_mask.any()):
            outlier_values = tensor[..., self.outlier_mask].to(dtype=torch.float16)

        return QuantizedTensorState(
            packed_indices=packed,
            norms=norms,
            regular_dim=regular.shape[-1],
            storage_bits=self.quantizer.storage_bits,
            requested_bits=self.quantizer.requested_bits,
            outlier_values=outlier_values,
        )

    def _append_state(
        self,
        existing: QuantizedTensorState | None,
        new_state: QuantizedTensorState,
    ) -> QuantizedTensorState:
        if existing is None:
            return new_state

        outlier_values = None
        if existing.outlier_values is not None and new_state.outlier_values is not None:
            outlier_values = torch.cat([existing.outlier_values, new_state.outlier_values], dim=2)

        return QuantizedTensorState(
            packed_indices=torch.cat([existing.packed_indices, new_state.packed_indices], dim=2),
            norms=torch.cat([existing.norms, new_state.norms], dim=2),
            regular_dim=new_state.regular_dim,
            storage_bits=new_state.storage_bits,
            requested_bits=new_state.requested_bits,
            outlier_values=outlier_values,
        )

    def _state_size_bytes(self, state: QuantizedTensorState | None) -> int:
        if state is None:
            return 0
        total = state.packed_indices.numel() * state.packed_indices.element_size()
        total += state.norms.numel() * state.norms.element_size()
        if state.outlier_values is not None:
            total += state.outlier_values.numel() * state.outlier_values.element_size()
        return int(total)

    def update(
        self,
        key_states: torch.Tensor,
        value_states: torch.Tensor,
        *args,
        **kwargs,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if not self.is_initialized:
            self.lazy_initialization(key_states, value_states)

        k_new = self._quantize_tensor(key_states)
        v_new = self._quantize_tensor(value_states)
        self.k_state = self._append_state(self.k_state, k_new)
        self.v_state = self._append_state(self.v_state, v_new)

        step_bytes = (
            key_states.numel() * key_states.element_size()
            + value_states.numel() * value_states.element_size()
        )
        self.baseline_bytes += int(step_bytes)
        self.compressed_bytes = self._state_size_bytes(self.k_state) + self._state_size_bytes(
            self.v_state
        )
        self.seq_length += int(key_states.shape[-2])
        if kwargs.get("return_full_states", True):
            return self.materialize(self.k_state), self.materialize(self.v_state)
        return key_states, value_states

    def materialize(self, state: QuantizedTensorState | None) -> torch.Tensor:
        if state is None:
            raise ValueError("Cannot materialize an empty quantized state")
        assert self.quantizer is not None
        assert self.regular_mask is not None
        assert self.outlier_mask is not None
        assert self.device is not None
        assert self.dtype is not None

        indices = _unpack_bits(state.packed_indices, state.storage_bits, state.regular_dim).to(
            self.device
        )
        centroids = self._quantizer_centroids(self.device, torch.float32)
        rotation = self._quantizer_rotation(self.device, torch.float32)
        regular = (centroids[indices] * state.norms.to(self.device).unsqueeze(-1)) @ rotation

        output = torch.zeros(
            *regular.shape[:-1],
            self.full_dim,
            dtype=torch.float32,
            device=self.device,
        )
        output[..., self.regular_mask.to(self.device)] = regular
        if bool(self.outlier_mask.any()) and state.outlier_values is not None:
            output[..., self.outlier_mask.to(self.device)] = state.outlier_values.to(
                self.device,
                dtype=torch.float32,
            )
        return output.to(dtype=self.dtype)

    def get_mask_sizes(self, query_length: int) -> tuple[int, int]:
        return self.seq_length + query_length, 0

    def get_seq_length(self) -> int:
        return self.seq_length

    def get_max_cache_shape(self) -> int:
        return -1

    def reorder_cache(self, beam_idx: torch.LongTensor) -> None:
        if self.k_state is not None:
            self.k_state = QuantizedTensorState(
                packed_indices=self.k_state.packed_indices.index_select(0, beam_idx),
                norms=self.k_state.norms.index_select(0, beam_idx),
                regular_dim=self.k_state.regular_dim,
                storage_bits=self.k_state.storage_bits,
                requested_bits=self.k_state.requested_bits,
                outlier_values=(
                    self.k_state.outlier_values.index_select(0, beam_idx)
                    if self.k_state.outlier_values is not None
                    else None
                ),
            )
        if self.v_state is not None:
            self.v_state = QuantizedTensorState(
                packed_indices=self.v_state.packed_indices.index_select(0, beam_idx),
                norms=self.v_state.norms.index_select(0, beam_idx),
                regular_dim=self.v_state.regular_dim,
                storage_bits=self.v_state.storage_bits,
                requested_bits=self.v_state.requested_bits,
                outlier_values=(
                    self.v_state.outlier_values.index_select(0, beam_idx)
                    if self.v_state.outlier_values is not None
                    else None
                ),
            )

    def crop(self, max_length: int) -> None:
        if self.seq_length == 0:
            return
        if max_length < 0:
            max_length = self.seq_length - abs(max_length)
        if self.seq_length <= max_length:
            return
        assert self.k_state is not None and self.v_state is not None
        self.k_state = QuantizedTensorState(
            packed_indices=self.k_state.packed_indices[:, :, :max_length, :],
            norms=self.k_state.norms[:, :, :max_length],
            regular_dim=self.k_state.regular_dim,
            storage_bits=self.k_state.storage_bits,
            requested_bits=self.k_state.requested_bits,
            outlier_values=(
                self.k_state.outlier_values[:, :, :max_length, :]
                if self.k_state.outlier_values is not None
                else None
            ),
        )
        self.v_state = QuantizedTensorState(
            packed_indices=self.v_state.packed_indices[:, :, :max_length, :],
            norms=self.v_state.norms[:, :, :max_length],
            regular_dim=self.v_state.regular_dim,
            storage_bits=self.v_state.storage_bits,
            requested_bits=self.v_state.requested_bits,
            outlier_values=(
                self.v_state.outlier_values[:, :, :max_length, :]
                if self.v_state.outlier_values is not None
                else None
            ),
        )
        self.seq_length = max_length
        self.compressed_bytes = self._state_size_bytes(self.k_state) + self._state_size_bytes(
            self.v_state
        )

    def batch_repeat_interleave(self, repeats: int) -> None:
        if self.k_state is not None:
            self.k_state = QuantizedTensorState(
                packed_indices=self.k_state.packed_indices.repeat_interleave(repeats, dim=0),
                norms=self.k_state.norms.repeat_interleave(repeats, dim=0),
                regular_dim=self.k_state.regular_dim,
                storage_bits=self.k_state.storage_bits,
                requested_bits=self.k_state.requested_bits,
                outlier_values=(
                    self.k_state.outlier_values.repeat_interleave(repeats, dim=0)
                    if self.k_state.outlier_values is not None
                    else None
                ),
            )
        if self.v_state is not None:
            self.v_state = QuantizedTensorState(
                packed_indices=self.v_state.packed_indices.repeat_interleave(repeats, dim=0),
                norms=self.v_state.norms.repeat_interleave(repeats, dim=0),
                regular_dim=self.v_state.regular_dim,
                storage_bits=self.v_state.storage_bits,
                requested_bits=self.v_state.requested_bits,
                outlier_values=(
                    self.v_state.outlier_values.repeat_interleave(repeats, dim=0)
                    if self.v_state.outlier_values is not None
                    else None
                ),
            )

    def batch_select_indices(self, indices: torch.Tensor) -> None:
        if self.k_state is not None:
            self.k_state = QuantizedTensorState(
                packed_indices=self.k_state.packed_indices.index_select(0, indices),
                norms=self.k_state.norms.index_select(0, indices),
                regular_dim=self.k_state.regular_dim,
                storage_bits=self.k_state.storage_bits,
                requested_bits=self.k_state.requested_bits,
                outlier_values=(
                    self.k_state.outlier_values.index_select(0, indices)
                    if self.k_state.outlier_values is not None
                    else None
                ),
            )
        if self.v_state is not None:
            self.v_state = QuantizedTensorState(
                packed_indices=self.v_state.packed_indices.index_select(0, indices),
                norms=self.v_state.norms.index_select(0, indices),
                regular_dim=self.v_state.regular_dim,
                storage_bits=self.v_state.storage_bits,
                requested_bits=self.v_state.requested_bits,
                outlier_values=(
                    self.v_state.outlier_values.index_select(0, indices)
                    if self.v_state.outlier_values is not None
                    else None
                ),
            )

    def compression_ratio(self) -> float | None:
        if self.compressed_bytes <= 0:
            return None
        return self.baseline_bytes / self.compressed_bytes

    def summary(self) -> dict[str, int | float]:
        ratio = self.compression_ratio() or 1.0
        outliers = int(self.outlier_mask.sum().item()) if self.outlier_mask is not None else 0
        return {
            "seq_length": self.seq_length,
            "baseline_bytes": int(self.baseline_bytes),
            "compressed_bytes": int(self.compressed_bytes),
            "compression_ratio": round(float(ratio), 3),
            "outlier_channels": outliers,
        }


class QuantizedAttention:
    def forward(
        self,
        module: Any,
        query: torch.Tensor,
        key_state: QuantizedTensorState,
        value_state: QuantizedTensorState,
        cache_layer: TurboQuantCacheLayer,
        attention_mask: torch.Tensor | None,
        *,
        scaling: float,
        dropout: float,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        assert cache_layer.quantizer is not None
        assert cache_layer.regular_mask is not None
        assert cache_layer.outlier_mask is not None

        batch, num_heads, query_len, _ = query.shape
        kv_heads = key_state.packed_indices.shape[1]
        groups = module.num_key_value_groups
        if num_heads != kv_heads * groups:
            raise ValueError(
                f"Query heads ({num_heads}) do not match kv heads ({kv_heads}) × groups ({groups})"
            )

        regular_mask = cache_layer.regular_mask.to(device=query.device)
        outlier_mask = cache_layer.outlier_mask.to(device=query.device)
        regular_dim = int(regular_mask.sum().item())

        query_grouped = query.view(batch, kv_heads, groups, query_len, cache_layer.full_dim)
        query_regular = query_grouped[..., regular_mask].to(torch.float32)
        query_outliers = (
            query_grouped[..., outlier_mask].to(torch.float32) if bool(outlier_mask.any()) else None
        )

        rotation = cache_layer._quantizer_rotation(query.device, query_regular.dtype)
        centroids = cache_layer._quantizer_centroids(query.device, query_regular.dtype)
        query_rot = query_regular @ rotation.T

        score_regular = self._regular_scores(query_rot, key_state, centroids)
        if query_outliers is not None and key_state.outlier_values is not None:
            score_outliers = torch.einsum(
                "bhgqd,bhsd->bhgqs",
                query_outliers,
                key_state.outlier_values.to(device=query.device, dtype=torch.float32),
            )
            scores = score_regular + score_outliers
        else:
            scores = score_regular

        attn_weights = scores.reshape(batch, num_heads, query_len, -1) * scaling
        if attention_mask is not None:
            attn_weights = attn_weights + attention_mask

        attn_weights = functional.softmax(attn_weights, dim=-1, dtype=torch.float32).to(query.dtype)
        attn_weights = functional.dropout(attn_weights, p=dropout, training=module.training)

        attn_grouped = attn_weights.view(batch, kv_heads, groups, query_len, -1).to(torch.float32)
        output_regular_rot = self._regular_values(attn_grouped, value_state, centroids)
        output_regular = output_regular_rot[..., :regular_dim] @ rotation

        output = torch.zeros(
            batch,
            kv_heads,
            groups,
            query_len,
            cache_layer.full_dim,
            dtype=query.dtype,
            device=query.device,
        )
        output[..., regular_mask] = output_regular.to(query.dtype)

        if bool(outlier_mask.any()) and value_state.outlier_values is not None:
            output[..., outlier_mask] = torch.einsum(
                "bhgqs,bhsd->bhgqd",
                attn_grouped,
                value_state.outlier_values.to(device=query.device, dtype=torch.float32),
            ).to(query.dtype)

        output = output.reshape(batch, num_heads, query_len, cache_layer.full_dim)
        return output.transpose(1, 2).contiguous(), attn_weights

    def _regular_scores(
        self,
        query_rot: torch.Tensor,
        state: QuantizedTensorState,
        centroids: torch.Tensor,
    ) -> torch.Tensor:
        packed = state.packed_indices.to(device=query_rot.device)
        indices = _unpack_bits(packed, state.storage_bits, state.regular_dim)
        centroid_values = centroids[indices]
        norms = state.norms.to(device=query_rot.device, dtype=torch.float32)
        return torch.einsum("bhgqd,bhsd,bhs->bhgqs", query_rot, centroid_values, norms)

    def _regular_values(
        self,
        attn_grouped: torch.Tensor,
        state: QuantizedTensorState,
        centroids: torch.Tensor,
    ) -> torch.Tensor:
        packed = state.packed_indices.to(device=attn_grouped.device)
        indices = _unpack_bits(packed, state.storage_bits, state.regular_dim)
        centroid_values = centroids[indices]
        norms = state.norms.to(device=attn_grouped.device, dtype=torch.float32)
        return torch.einsum("bhgqs,bhsd,bhs->bhgqd", attn_grouped, centroid_values, norms)


class TurboQuantCache(DynamicCache):
    def __init__(
        self,
        bits: float = 3.5,
        outlier_threshold: float = 10.0,
        *,
        num_hidden_layers: int | None = None,
    ) -> None:
        self.bits = bits
        self.outlier_threshold = outlier_threshold
        self.num_hidden_layers = num_hidden_layers
        self.quantized_attention = QuantizedAttention()
        layers = []
        if num_hidden_layers is not None:
            layers = [
                TurboQuantCacheLayer(bits=bits, outlier_threshold=outlier_threshold, seed=layer_idx)
                for layer_idx in range(num_hidden_layers)
            ]
            Cache.__init__(self, layers=layers)
        else:
            Cache.__init__(self, layers=[])

    def update(
        self,
        key_states: torch.Tensor,
        value_states: torch.Tensor,
        layer_idx: int,
        *args,
        **kwargs,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        while len(self.layers) <= layer_idx:
            self.layers.append(
                TurboQuantCacheLayer(
                    bits=self.bits,
                    outlier_threshold=self.outlier_threshold,
                    seed=len(self.layers),
                )
            )
        return self.layers[layer_idx].update(key_states, value_states, *args, **kwargs)

    def memory_stats(self) -> dict[str, object]:
        attention_layers = [
            layer for layer in self.layers if isinstance(layer, TurboQuantCacheLayer)
        ]
        baseline = sum(layer.baseline_bytes for layer in attention_layers)
        compressed = sum(layer.compressed_bytes for layer in attention_layers)
        ratios = [
            layer.compression_ratio() for layer in attention_layers if layer.compression_ratio()
        ]
        seq_lengths = [layer.seq_length for layer in attention_layers if layer.seq_length > 0]
        return {
            "layers_initialized": sum(1 for layer in attention_layers if layer.is_initialized),
            "baseline_mb": round(baseline / (1024 * 1024), 3),
            "compressed_mb": round(compressed / (1024 * 1024), 3),
            "compression_ratio": round(float(sum(ratios) / len(ratios)), 3) if ratios else 1.0,
            "max_seq_length": max(seq_lengths) if seq_lengths else 0,
            "per_layer": [layer.summary() for layer in attention_layers if layer.is_initialized],
        }

    def get_max_length(self) -> int | None:
        max_shape = self.get_max_cache_shape()
        return None if max_shape < 0 else max_shape


def _patch_gemma_attention_forward(module) -> None:
    from transformers.cache_utils import Cache as HFCache
    from transformers.modeling_attention_utils import ALL_ATTENTION_FUNCTIONS
    from transformers.models.gemma3.modeling_gemma3 import (
        apply_rotary_pos_emb,
        eager_attention_forward,
    )

    original_forward = module.forward

    def _forward(
        self,
        hidden_states: torch.Tensor,
        position_embeddings: torch.Tensor = None,
        attention_mask: torch.Tensor | None = None,
        past_key_values: HFCache | None = None,
        **kwargs,
    ):
        input_shape = hidden_states.shape[:-1]
        hidden_shape = (*input_shape, -1, self.head_dim)

        query_states = self.q_proj(hidden_states).view(hidden_shape).transpose(1, 2)
        key_states = self.k_proj(hidden_states).view(hidden_shape).transpose(1, 2)
        value_states = self.v_proj(hidden_states).view(hidden_shape).transpose(1, 2)

        query_states = self.q_norm(query_states)
        key_states = self.k_norm(key_states)

        cos, sin = position_embeddings
        query_states, key_states = apply_rotary_pos_emb(query_states, key_states, cos, sin)

        if isinstance(past_key_values, TurboQuantCache):
            past_key_values.update(
                key_states,
                value_states,
                self.layer_idx,
                return_full_states=False,
            )
            cache_layer = past_key_values.layers[self.layer_idx]
            attn_output, attn_weights = past_key_values.quantized_attention.forward(
                self,
                query_states,
                cache_layer.k_state,
                cache_layer.v_state,
                cache_layer,
                attention_mask,
                scaling=self.scaling,
                dropout=self.attention_dropout if self.training else 0.0,
            )
            attn_output = attn_output.reshape(*input_shape, -1).contiguous()
            attn_output = self.o_proj(attn_output)
            return attn_output, attn_weights

        if past_key_values is not None:
            key_states, value_states = past_key_values.update(
                key_states, value_states, self.layer_idx
            )

        attention_interface = ALL_ATTENTION_FUNCTIONS.get_interface(
            self.config._attn_implementation, eager_attention_forward
        )
        attn_output, attn_weights = attention_interface(
            self,
            query_states,
            key_states,
            value_states,
            attention_mask,
            dropout=self.attention_dropout if self.training else 0.0,
            scaling=self.scaling,
            sliding_window=self.sliding_window,
            **kwargs,
        )

        attn_output = attn_output.reshape(*input_shape, -1).contiguous()
        attn_output = self.o_proj(attn_output)
        return attn_output, attn_weights

    if getattr(module, "_turboquant_patched", False):
        return
    module._turboquant_original_forward = original_forward
    module.forward = MethodType(_forward, module)
    module._turboquant_patched = True


def patch_model_for_quantized_attention(model) -> None:
    patched = 0
    for module in model.modules():
        if module.__class__.__name__ == "Gemma3Attention":
            _patch_gemma_attention_forward(module)
            patched += 1
    if patched == 0:
        raise RuntimeError("No Gemma3Attention modules found to patch for QuantizedAttention")
