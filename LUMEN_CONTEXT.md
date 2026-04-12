# Lumen — Technical Context

> Consolidated technical sources, findings, and implementation-relevant information collected during research phase. This document is the single source of truth for implementation decisions.

---

## 1. TurboQuant — The Algorithm

### Source
- **Paper:** Zandieh, Daliri, Hadian, Mirrokni. *"TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate"* — ICLR 2026
- **arXiv:** https://arxiv.org/abs/2504.19874
- **Google Research Blog:** https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/

### What It Does
TurboQuant is an online (data-oblivious) vector quantization algorithm that compresses high-dimensional vectors to 2.5–4 bits per coordinate with near-zero distortion. Two primary applications:
1. **KV cache compression** — reduces key-value memory during LLM inference
2. **Vector search** — compresses embedding indices for faster similarity lookup

### Algorithm — Step by Step

**TurboQuantMSE (MSE-optimal):**
1. Normalize input vector `x` to unit sphere → `x_hat`, save `norm`
2. Apply random orthogonal rotation: `y = Pi @ x_hat` — this induces a Beta distribution on each coordinate, making them near-independent in high dimensions
3. Apply Lloyd-Max scalar quantizer per coordinate (codebook precomputed from the known Beta distribution — no calibration needed)
4. Store: `{indices: uint8, norm: float32}`

**TurboQuantProd (inner-product-optimal, two-stage):**
1. Apply TurboQuantMSE with `(b-1)` bits
2. Compute residual: `residual = x_hat - dequantize(mse_result)`
3. Apply QJL (Quantized Johnson-Lindenstrauss) 1-bit transform on the residual
4. Store: `{mse_indices, qjl_signs, residual_norm, input_norm}`

**QJL (1-bit Quantized Johnson-Lindenstrauss):**
- Projects vector through random sign matrix `S`
- Reduces each coordinate to a single sign bit (+1 or -1)
- Zero memory overhead
- Provides unbiased inner product estimation

### Formal Distortion Bounds (from paper)

| Bit-width | MSE bound | Empirical (d=1536) |
|---|---|---|
| 1-bit | 0.360 | 0.363 |
| 2-bit | 0.117 | 0.117 |
| 3-bit | 0.030 | 0.035 |
| 4-bit | 0.009 | 0.009 |

TurboQuant is within ~2.7x of the information-theoretic Shannon lower bound — meaning there is essentially no headroom left for competing algorithms.

### KV Cache Compression Results (paper)
- **3.5-bit:** absolute quality neutrality (zero measurable loss)
- **2.5-bit:** marginal quality degradation
- **Speedup:** up to 8x on H100 GPU for attention logit computation (note: community implementations achieve ~1.85x — see limitations)

---

## 2. Supporting Algorithms

### PolarQuant
- **arXiv:** https://arxiv.org/abs/2502.02617 (AISTATS 2026)
- Converts Cartesian vectors to polar coordinates — eliminates memory overhead of quantization constants
- Used internally by TurboQuant as the MSE compression stage in some configurations
- Key insight: maps data onto a fixed circular grid where boundaries are known, eliminating the normalization step

### QJL (Quantized Johnson-Lindenstrauss)
- **arXiv:** https://arxiv.org/abs/2406.03482 (AAAI 2025)
- 1-bit inner product quantization via Johnson-Lindenstrauss Transform
- Zero memory overhead (no quantization constants to store)
- Provides **unbiased** inner product estimation: `E[<y, Q^-1(Q(x))>] = <y, x>`

---

## 3. Community Implementations

### OmarHory/turboquant
- **URL:** https://github.com/OmarHory/turboquant
- **License:** MIT
- **Status:** Full GPU implementation, Triton CUDA kernels, tested on A100 and A40
- **Language:** Python (PyTorch + Triton)

**Implemented components:**

| Component | File | Notes |
|---|---|---|
| `TurboQuantMSE` | `turboquant/core.py` | Algorithm 1 from paper |
| `QJL` | `turboquant/core.py` | 1-bit QJL transform |
| `TurboQuantProd` | `turboquant/core.py` | Algorithm 2 — do not use as default |
| `TurboQuantCache` | `turboquant/cache.py` | KV cache with outlier-aware quantization |
| `TQLayerFused` | `turboquant/cache.py` | Compressed indices for quantized attention |
| `QuantizedAttention` | `turboquant/attention.py` | Q@K^T on compressed indices, no dequant |
| `FusedQuantizedAttentionCUDA` | `turboquant/cuda_kernels.py` | Triton kernel |
| Bit-packing | `turboquant/packing.py` | 2/3/4-bit into bytes |

**Memory layout:** `block = 52 bytes per 128-value vector at 3-bit` (4 bytes norm + 48 bytes packed indices)

**Attention pipeline:**
```
Quantize:   x  →  Pi @ x  →  bucketize  →  uint8 indices
Attention:  Q  →  Q @ Pi^T  →  matmul(centroids[idx])  →  scores
```

**Benchmark results (Mistral-7B-Instruct-v0.3, A100):**
- 3.8–5.7x KV memory compression at 4-bit and 3.5-bit with matching generation quality
- 1.85x quantized attention speedup vs dequantize-then-matmul at 16K sequence length

**Benchmark commands:**
```bash
python -m benchmarks.validate_algorithms     # 30 checks vs paper bounds
python -m benchmarks.eval_needle             # Needle-in-haystack 4K–16K
python -m benchmarks.eval_longbench          # LongBench-E, 12 tasks
```

**Known limitation:** Paper reports 8x speedup; implementation achieves 1.85x. Gap is due to missing authors' optimized CUDA kernels (not released).

---

### scos-lab/turboquant
- **URL:** https://github.com/scos-lab/turboquant
- **License:** MIT
- **Status:** Pure NumPy/CPU reference implementation, not for production GPU use
- **Value:** Contains engineering findings NOT in the paper — critical for correct implementation

**File structure:**
```
core.py              — TurboQuantMSE + TurboQuantProd
rotation.py          — Random orthogonal rotation
scalar_quantizer.py  — Beta distribution optimal quantizer (Lloyd's algorithm)
qjl.py               — Quantized Johnson-Lindenstrauss (1-bit)
mixed_precision.py   — Outlier-aware mixed precision
kv_cache.py          — HuggingFace transformers Cache integration
compressed_cache.py  — Actual compressed storage (real memory savings)
```

**Core code reference (`core.py`):**
```python
@dataclass(frozen=True)
class QuantizedMSE:
    indices: np.ndarray  # uint8
    norms: np.ndarray    # float32

class TurboQuantMSE:
    def __init__(self, d: int, b: int, seed=None):
        self.rotation = generate_rotation(d, seed)
        self.centroids, self.boundaries = compute_centroids(d, b)  # Lloyd-Max for Beta dist

    def quantize(self, x):
        x_hat, norms = normalize(x)
        y = rotate(x_hat, self.rotation)                    # Beta distribution induced
        indices = quantize_scalar(y, self.boundaries)       # optimal per-coordinate
        return QuantizedMSE(indices=indices, norms=norms)

class TurboQuantProd:
    def __init__(self, d: int, b: int, seed=None):
        self.mse_quantizer = TurboQuantMSE(d, b-1, seed)   # b-1 bits for MSE
        self.S = generate_projection(d, qjl_seed)           # 1 bit for QJL residual

    def quantize(self, x):
        x_hat, input_norms = normalize(x)
        q_mse = self.mse_quantizer.quantize(x_hat)
        x_mse = self.mse_quantizer.dequantize(q_mse)
        residual = x_hat - x_mse
        signs = qjl_quantize(residual, self.S)
        return QuantizedProd(mse_indices, qjl_signs, residual_norm, input_norms)
```

---

### turboquant-mlx (sharpner)
- **URL:** https://github.com/sharpner/turboquant-mlx
- **Platform:** Apple Silicon (MLX framework)
- **Value:** Only implementation tested specifically on Gemma 4 with head_dim=256

**Key finding for Lumen (Gemma 4 E4B, head_dim=256):**
- `3-bit rot+QJL` beats fp16 baseline on Gemma 4 — PPL 12.05 vs 12.18 (-1.1% improvement)
- Rotation + QJL acts as regularizer at D=256
- `TurboQuantProd` (2-bit MSE + QJL) consistently degrades quality at D=128 AND D=256
- Root cause: centroid resolution loss through softmax amplification
- QJL works as extra information (V2 3-bit rot+QJL: +5.3% vs +6.6% without QJL), not as replacement for MSE bits

**Architecture:**
```
V2 Path (Speed):   mx.quantize affine ± rotation ± QJL  → Metal kernel (quantized_matmul)
V3 Path (Quality): Lloyd-Max codebook + rotation ± channel split → software dequant
```

---

### Incept5/gemma4-benchmark
- **URL:** https://github.com/Incept5/gemma4-benchmark
- **Value:** TurboQuant benchmarks on all Gemma 4 models including E4B, on Apple Silicon

**TurboQuant decode speedup by context length:**
- Negligible at < 16K tokens
- +5–10% at 32–64K
- +15–19% at 128–256K on larger models (26B, 31B, E4B)
- Negative on E2B — model weights so small that quantization overhead dominates

---

### llama.cpp Discussion #20969
- **URL:** https://github.com/ggml-org/llama.cpp/discussions/20969
- **Status (as of April 2026):** C implementation complete (18/18 tests passing), CUDA kernels written awaiting GPU validation, integration pending merge

**Validated results:**
- TQ3 (3-bit): MSE = 0.034 (paper: 0.034), 4.9x compression vs FP16
- TQ4 (4-bit): MSE = 0.009 (paper: 0.009), 3.8x compression vs FP16

**Gemma 4 specific note from discussion:** Global attention layers (head_dim=512 in some configs) fall through to TILE FA kernel — proper VEC dequant made accuracy worse. TILE fallback acts as effective layer dropout, less harmful than structured quantization noise.

---

## 4. Engineering Findings NOT in the Paper

Source: scos-lab/turboquant `BENCHMARK_RESULTS.md` + turboquant-mlx experiments

### Finding 1 — K/V Norm Disparity (Critical)

Modern LLMs have dramatically different Key vs Value vector magnitudes. Quantization error scales with norm squared, so K vectors need far more bits than V.

| Model | K mean norm | V mean norm | Ratio |
|---|---|---|---|
| GPT-2 (124M) | 11.8 | 2.0 | 6x |
| Phi-2 (2.8B) | 13.1 | 3.0 | 4x |
| Qwen2.5-3B | 172.1 | 3.3 | 52x |
| Qwen2.5-7B | 274.0 | 2.6 | 106x |
| Qwen2.5-1.5B | 778.6 | 4.3 | 182x |
| Qwen2.5-0.5B | 259.3 | 0.2 | 1274x |

**Note for Lumen:** Gemma 4 architecture sets K=V for global attention layers by design — this is explicitly documented in the Gemma 4 architecture. This means K/V ratio is effectively 1x on global layers, making Gemma 4 the most favorable case for TurboQuant.

### Finding 2 — MSE beats Prod in practice (contradicts paper recommendation)

**Paper recommends:** TurboQuantProd for Keys, TurboQuantMSE for Values
**Empirical result:** TurboQuantMSE for both is better

| GPT-2, b=4 | PPL change |
|---|---|
| MSE for both K and V | +1.1% |
| Paper config (Prod keys) | +6.5% |

**Why:** TurboQuantProd's QJL residual correction adds variance. Softmax attention amplifies variance more than bias. Low variance (MSE) beats unbiasedness (Prod) in practice.

**For Lumen:** Always use TurboQuantMSE for both K and V on Gemma 4 E4B.

### Finding 3 — Outlier-Aware Mixed Precision

~5–20% of K channels have RMS 10–100x larger than the median (especially Layer 0).

**Mixed precision strategy:**
- Outlier channels (top 5–20% by RMS): 8-bit
- Regular channels: 3-bit
- Result: 3.6 bits effective average, +2.1% PPL on Qwen2.5-1.5B (target was 3.5-bit at 0.0%)

### Finding 4 — K/V Ratio Predicts Optimal Bit Budget

```
K/V ratio < 10x    → 3-bit uniform works      (GPT-2, Gemma 4 global layers)
K/V ratio 10-60x   → 4.5-5 bit asymmetric
K/V ratio > 100x   → 5.5+ bit or mixed prec.
K/V ratio > 1000x  → TurboQuant alone insufficient
```

### Finding 5 — Real Memory Compression Numbers

Tested on GPT-2 (41 tokens, 12 layers):
- FP32 KV cache: 2,952 KB
- Compressed: 327 KB
- **Reduction: 89% (9x compression), zero PPL impact**

---

## 5. Gemma 4 E4B — Architecture Details

### Sources
- Google AI for Developers: https://ai.google.dev/gemma/docs/core
- HuggingFace blog: https://huggingface.co/blog/gemma4
- Visual Guide by Maarten Grootendorst: https://newsletter.maartengrootendorst.com/p/a-visual-guide-to-gemma-4

### Architecture Characteristics Relevant to TurboQuant

| Property | Value | TurboQuant Implication |
|---|---|---|
| Architecture | Dense (not MoE) | Standard KV cache, no expert routing complexity |
| head_dim | 256 (vs 128 in Llama/Mistral) | Lloyd-Max codebooks must be precomputed for d=256; better Beta concentration |
| Attention pattern | 5:1 (5 local sliding-window + 1 global) | KV cache mainly from global layers |
| K=V in global layers | Yes (by design in Gemma 4) | K/V ratio ≈ 1x on critical layers — best case for uniform bit allocation |
| Context window | 128K tokens | Sessions up to 128K viable with TurboQuant |
| Sliding window size | 512 tokens (local layers) | Local layers have small KV cache — compression benefit mainly on global layers |

### Memory Requirements

| Precision | VRAM needed |
|---|---|
| BF16 (baseline) | ~10 GB |
| 4-bit weights | ~5 GB |
| 4-bit weights + TurboQuant 3.5-bit KV | ~3-4 GB + session KV |

### TurboQuant Native Support Confirmed

**mlx-vlm (Apple Silicon):**
```bash
mlx_vlm.generate \
  --model "mlx-community/gemma-4-E4B-it-4bit" \
  --kv-bits 3.5 \
  --kv-quant-scheme turboquant
```

**Benchmark results (Gemma 4 26B at 128K context):**
- KV Memory: 13.3 GB → 4.9 GB (63% reduction)
- Peak Memory: 75.2 GB → 65.8 GB (-9.4 GB)
- Quality: preserved

**Benchmark results (MLX, Gemma 4 26B):**
- 5.22x KV cache compression, stable across all tested prompt lengths

**Decode speedup on Gemma 4 E4B:**
- +15–19% at 128–256K context length
- Negligible at < 16K (quantization overhead dominates at short contexts)

---

## 6. Integration Path for WSL2/Docker (Lumen target environment)

### Recommended Stack

```
OmarHory/turboquant          ← GPU implementation (PyTorch + Triton)
HuggingFace Transformers     ← model loading and inference
FAISS                        ← vector index for RAG corpus
pgvector (optional)          ← persistent vector storage
FastAPI                      ← API layer
Docker + WSL2 + NVIDIA GPU   ← runtime environment
```

### Integration Hook Pattern

```python
# Monkey-patch approach — no model file modification needed
import mlx_lm.models.cache as cache_module
from turboquant.cache import TurboQuantCache

cache_module.make_prompt_cache = lambda model, **kw: [
    TurboQuantCache(bits=3.5) for _ in range(len(model.layers))
]

# Load and run normally — compression is transparent
model, tokenizer = load("google/gemma-4-E4B-it")
```

### llama.cpp Path (pending)
- C implementation: 18/18 tests passing, MSE within 1% of paper
- CUDA kernels: written, awaiting GPU validation
- Integration: 6-phase plan covering GGML type registration, KV cache paths, flash attention
- Status: pending merge as of April 2026 — monitor https://github.com/ggml-org/llama.cpp/discussions/20969

---

## 7. Lumen-Specific Technical Decisions

### Decision 1 — Use TurboQuantMSE for both K and V
**Rationale:** Empirically confirmed across multiple models and implementations. QJL adds variance amplified by softmax. On Gemma 4 (head_dim=256), MSE-only actually beats fp16 baseline in perplexity.

### Decision 2 — 3.5-bit uniform + outlier mixed precision
**Rationale:** Native support in mlx-vlm for Gemma 4. Zero-loss confirmed. ~5x compression confirmed in benchmarks. Mixed precision (8-bit on outlier channels) for layers with high RMS disparity.

### Decision 3 — Corpus indexing at semantic unit granularity
**Rationale:** O Livro dos Espíritos has 1,019 numbered questions — each question is the minimum meaningful unit for Kardec's doctrine. Chunking at question level enables precise citation and cleaner RAG recall. Narrative works (Emmanuel, Joanna) use paragraph-level chunks with 2-paragraph overlap.

### Decision 4 — FAISS with inner product search (not cosine)
**Rationale:** TurboQuant is optimized for inner product preservation. Using cosine similarity would add a normalization step that partially negates the quantization design.

### Decision 5 — Gemma 4 E4B as base model (not larger variants)
**Rationale:** Runs on consumer GPU (4-6 GB VRAM at 4-bit weights + TurboQuant KV). 128K context window sufficient for Lumen sessions. Dense architecture (not MoE) — simpler KV cache management. Confirmed TurboQuant support. For future expansion to 26B MoE, the same TurboQuant integration applies.

---

## 8. Corpus Notes

### Allan Kardec — Works and Structure

| Obra | Questões/Capítulos | Estrutura | Domínio Público |
|---|---|---|---|
| O Livro dos Espíritos | 1,019 questões numeradas | Q&A por parte e capítulo | Sim |
| O Livro dos Médiuns | 334 artigos | Narrativo + Q&A | Sim |
| O Evangelho Segundo o Espiritismo | 28 capítulos | Narrativo + comentário | Sim |
| O Céu e o Inferno | 2 partes | Narrativo + casos | Sim |
| A Gênese | 19 capítulos | Narrativo científico | Sim |
| Revista Espírita | Artigos mensais 1858–1869 | Artigos | Sim |

**Chunking strategy for O Livro dos Espíritos:**
```json
{
  "id": "lde-q223",
  "autor": "Allan Kardec",
  "medium": null,
  "obra": "O Livro dos Espíritos",
  "parte": "Parte Segunda — Do Mundo Espírita",
  "capitulo": "I — Os Espíritos",
  "questao": 223,
  "texto": "...",
  "edicao_referencia": "FEB, 2013"
}
```

### Joanna de Angelis / Divaldo Franco
- Direitos: LEAL Editora (verificar licença antes de distribuir índices)
- Voz: poética, psicologia espiritual, metáforas
- Chunking: parágrafo + overlap 2 parágrafos

### Emmanuel / Chico Xavier
- Direitos: FEB — Federação Espírita Brasileira (verificar licença)
- Voz: fraternal, cristã espiritualizada
- Corpus extenso: mais de 400 obras psicografadas via Chico — selecionar obras canônicas de Emmanuel

---

## 9. Validation Benchmarks to Run

Before any production use, these benchmarks must pass:

```bash
# 1. Algorithm correctness (30 checks vs paper bounds)
python -m benchmarks.validate_algorithms

# 2. Gemma 4 E4B specific — head_dim=256 codebook validation
# Must show MSE within 1.2x of paper bounds at d=256

# 3. Memory compression at 128K context
# Target: ~5x KV compression, < 2% PPL degradation

# 4. Needle-in-haystack on Kardec corpus
# Target: > 95% recall at 4K, 16K, 64K, 128K

# 5. Citation precision
# 50 known Kardec questions → correct LdE question cited
# Target: > 90%
```

---

## 10. Key URLs Reference

| Resource | URL |
|---|---|
| TurboQuant paper | https://arxiv.org/abs/2504.19874 |
| TurboQuant HTML (full paper) | https://arxiv.org/html/2504.19874v1 |
| Google Research blog | https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/ |
| PolarQuant paper | https://arxiv.org/abs/2502.02617 |
| QJL paper | https://arxiv.org/abs/2406.03482 |
| OmarHory/turboquant | https://github.com/OmarHory/turboquant |
| scos-lab/turboquant | https://github.com/scos-lab/turboquant |
| turboquant-mlx | https://github.com/sharpner/turboquant-mlx |
| Incept5/gemma4-benchmark | https://github.com/Incept5/gemma4-benchmark |
| llama.cpp discussion | https://github.com/ggml-org/llama.cpp/discussions/20969 |
| Gemma 4 docs | https://ai.google.dev/gemma/docs/core |
| HuggingFace Gemma 4 blog | https://huggingface.co/blog/gemma4 |
| Visual Guide to Gemma 4 | https://newsletter.maartengrootendorst.com/p/a-visual-guide-to-gemma-4 |
| TurboQuant.net (analysis) | https://turboquant.net/ |
