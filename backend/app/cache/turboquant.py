"""
TurboQuantMSE foundations for Phase 2 retrieval compression.

This module implements the core pieces we need locally:
  - deterministic random orthogonal rotation
  - Lloyd-Max scalar quantizer over the unit-sphere coordinate density
  - packed index storage for compressed vectors

The implementation is intentionally CPU-first. It is designed to compress
OpenAI embedding vectors for persistence and retrieval experiments before the
more invasive Phase 2 KV-cache path lands.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


def _l2_normalize(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    norms = np.linalg.norm(vectors, axis=1).astype(np.float32)
    safe_norms = np.where(norms > 0, norms, 1.0).astype(np.float32)
    return vectors / safe_norms[:, None], norms


def _generate_rotation(dim: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    gaussian = rng.standard_normal((dim, dim), dtype=np.float32)
    q, r = np.linalg.qr(gaussian)
    signs = np.sign(np.diag(r))
    signs[signs == 0] = 1.0
    return (q * signs).astype(np.float32)


def _sphere_coordinate_pdf(dimension: int, grid: np.ndarray) -> np.ndarray:
    alpha = (dimension - 3) / 2
    density = np.power(np.clip(1.0 - grid**2, 0.0, None), alpha, dtype=np.float64)
    density /= np.trapz(density, grid)
    return density


def _compute_quantile_edges(cdf: np.ndarray, grid: np.ndarray, levels: int) -> np.ndarray:
    quantiles = np.linspace(0.0, 1.0, levels + 1)
    edges = np.interp(quantiles, cdf, grid)
    edges[0] = -1.0
    edges[-1] = 1.0
    return edges.astype(np.float32)


def _conditional_centroid(
    grid: np.ndarray, density: np.ndarray, left: float, right: float
) -> float:
    if right <= left:
        return float((left + right) / 2)

    mask = (grid >= left) & (grid <= right)
    if not np.any(mask):
        return float((left + right) / 2)

    x = grid[mask]
    p = density[mask]
    mass = np.trapz(p, x)
    if mass <= 1e-12:
        return float((left + right) / 2)
    centroid = np.trapz(x * p, x) / mass
    return float(centroid)


def _lloyd_max_codebook(
    dimension: int,
    levels: int,
    grid_size: int = 4097,
    max_iterations: int = 25,
    tolerance: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray]:
    grid = np.linspace(-1.0, 1.0, grid_size, dtype=np.float64)
    density = _sphere_coordinate_pdf(dimension, grid)
    cdf = np.cumsum(density)
    cdf /= cdf[-1]

    boundaries = _compute_quantile_edges(cdf, grid, levels)
    centroids = np.zeros(levels, dtype=np.float32)

    for _ in range(max_iterations):
        for idx in range(levels):
            centroids[idx] = _conditional_centroid(
                grid,
                density,
                float(boundaries[idx]),
                float(boundaries[idx + 1]),
            )

        updated = np.empty_like(boundaries)
        updated[0] = -1.0
        updated[-1] = 1.0
        updated[1:-1] = ((centroids[:-1] + centroids[1:]) / 2).astype(np.float32)

        if np.max(np.abs(updated - boundaries)) <= tolerance:
            boundaries = updated
            break
        boundaries = updated

    return centroids.astype(np.float32), boundaries.astype(np.float32)


def _pack_indices(indices: np.ndarray, bits: int) -> np.ndarray:
    vectors, dimension = indices.shape
    total_bits = dimension * bits
    packed_width = (total_bits + 7) // 8
    packed = np.zeros((vectors, packed_width), dtype=np.uint8)

    for row in range(vectors):
        bit_offset = 0
        for value in indices[row]:
            current = int(value)
            for shift in range(bits):
                if current & (1 << shift):
                    byte_idx = bit_offset // 8
                    bit_idx = bit_offset % 8
                    packed[row, byte_idx] |= np.uint8(1 << bit_idx)
                bit_offset += 1

    return packed


def _unpack_indices(packed: np.ndarray, bits: int, shape: tuple[int, int]) -> np.ndarray:
    vectors, dimension = shape
    indices = np.zeros(shape, dtype=np.uint8)

    for row in range(vectors):
        bit_offset = 0
        for col in range(dimension):
            value = 0
            for shift in range(bits):
                byte_idx = bit_offset // 8
                bit_idx = bit_offset % 8
                bit = (int(packed[row, byte_idx]) >> bit_idx) & 1
                value |= bit << shift
                bit_offset += 1
            indices[row, col] = value

    return indices


@dataclass(frozen=True)
class QuantizedMSE:
    packed_indices: np.ndarray
    norms: np.ndarray
    shape: tuple[int, int]
    requested_bits: float
    storage_bits: int


class TurboQuantMSE:
    """
    CPU implementation of the MSE-oriented TurboQuant path for embeddings.

    `bits` may be fractional in config/specs. Storage currently rounds up to the
    nearest integer bit-width for packed persistence.
    """

    def __init__(
        self,
        dim: int,
        bits: float = 3.5,
        seed: int = 0,
        *,
        rotation: np.ndarray | None = None,
        centroids: np.ndarray | None = None,
        boundaries: np.ndarray | None = None,
    ) -> None:
        self.dim = dim
        self.requested_bits = float(bits)
        self.storage_bits = math.ceil(bits)
        self.seed = seed
        self.levels = 2**self.storage_bits
        self.rotation = (
            np.asarray(rotation, dtype=np.float32)
            if rotation is not None
            else _generate_rotation(dim, seed)
        )
        if centroids is None or boundaries is None:
            self.centroids, self.boundaries = _lloyd_max_codebook(dim, self.levels)
        else:
            self.centroids = np.asarray(centroids, dtype=np.float32)
            self.boundaries = np.asarray(boundaries, dtype=np.float32)

    def quantize(self, vectors: np.ndarray) -> QuantizedMSE:
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim != 2:
            raise ValueError("Expected a 2D array of vectors")
        if array.shape[1] != self.dim:
            raise ValueError(f"Expected dimension {self.dim}, got {array.shape[1]}")

        normalized, norms = _l2_normalize(array)
        rotated = normalized @ self.rotation.T
        interior = self.boundaries[1:-1]
        indices = np.digitize(rotated, interior, right=False).astype(np.uint8)
        packed = _pack_indices(indices, self.storage_bits)
        return QuantizedMSE(
            packed_indices=packed,
            norms=norms.astype(np.float32),
            shape=indices.shape,
            requested_bits=self.requested_bits,
            storage_bits=self.storage_bits,
        )

    def dequantize(self, quantized: QuantizedMSE) -> np.ndarray:
        indices = _unpack_indices(quantized.packed_indices, quantized.storage_bits, quantized.shape)
        rotated = self.centroids[indices]
        restored = rotated @ self.rotation
        renormalized, _ = _l2_normalize(restored)
        return (renormalized * quantized.norms[:, None]).astype(np.float32)

    def serialize(self) -> dict[str, np.ndarray | float | int]:
        return {
            "dim": self.dim,
            "requested_bits": self.requested_bits,
            "storage_bits": self.storage_bits,
            "seed": self.seed,
            "rotation": self.rotation,
            "centroids": self.centroids,
            "boundaries": self.boundaries,
        }

    @classmethod
    def from_serialized(cls, state: dict[str, np.ndarray | float | int]) -> TurboQuantMSE:
        return cls(
            dim=int(state["dim"]),
            bits=float(state["requested_bits"]),
            seed=int(state.get("seed", 0)),
            rotation=np.asarray(state["rotation"], dtype=np.float32),
            centroids=np.asarray(state["centroids"], dtype=np.float32),
            boundaries=np.asarray(state["boundaries"], dtype=np.float32),
        )
