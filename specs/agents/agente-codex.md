# Code Agent Steering (agente-codex)

> **Role:** Implementation Agent for the Lumen Project
> **Primary Goal:** Write, modify, and maintain the codebase for the Lumen pipeline, ensuring strict adherence to the TurboQuant quantization rules and local system constraints.

---

## 1. Responsibilities

You are responsible for the hands-on implementation of the system modules:
- **`backend/app/corpus/`**: Parsing, chunking, embedding generation, and FAISS indexing.
- **`backend/app/llm/`**: Model loading (Gemma 4 E4B) and inference generation logic.
- **`backend/app/persona/`**: RAG pipeline orchestration, system prompt curation, and citation injection.
- **`backend/app/api/`**: FastAPI endpoints (`/api/chat`, `/api/search`) including SSE streaming.
- **`frontend/`**: Vanilla HTML/JS/Tailwind frontend integration connecting to the backend APIs.
- **`backend/tests/`**: Unit and integration tests for the above modules.

---

## 2. Required Domain Knowledge

Before writing any quantization or inference code, you must understand:

1. **Repository Structures**:
   - **OmarHory/turboquant**: The GPU implementation reference (PyTorch + Triton). Use this for actual pipeline integration.
   - **scos-lab/turboquant**: The NumPy-based reference and source of crucial empirical engineering findings.

2. **Algorithm Distinctions**:
   - `TurboQuantMSE`: Uses a random rotation and a Lloyd-Max scalar quantizer. **This is the mandatory quantizer for both Key and Value vectors in Lumen.**
   - `TurboQuantProd`: Uses MSE plus a Quantized Johnson-Lindenstrauss (QJL) residual correction. **Do not use this**, as empirical evidence shows the QJL variance degrades quality compared to pure MSE in practice.

3. **Memory Layout**:
   - A standard 128-value vector compressed at 3-bit precision occupies exactly **52 bytes** (4 bytes for the float32 norm + 48 packed bytes for the indices).
   - Do not dequantize the KV cache for intermediate operations. Use `QuantizedAttention` to compute $Q K^T$ directly on the compressed indices.

---

## 3. Mandatory Coding Patterns

When implementing TurboQuant data structures and logic, you **must** adhere to the following patterns:

- **Immutability**: Always use `dataclass(frozen=True)` for quantized representations.
  ```python
  from dataclasses import dataclass
  import numpy as np

  @dataclass(frozen=True)
  class QuantizedMSE:
      indices: np.ndarray   # uint8 packed indices
      norms: np.ndarray     # float32 norms
  ```
- **Rotation Matrix Separation**: The orthogonal rotation matrix ($\Pi$) must be generated once and separated from the core quantization logic.
- **Storage Rule**: **Never** store the rotation matrix alongside the compressed indices. It is a shared constant for the quantizer instance and doing so would defeat the memory compression benefits.

---

## 4. Documented Pitfalls & Constraints

1. **Head Dimension Mismatch**:
   - Gemma 4 E4B has `head_dim=256`.
   - The Lloyd-Max codebooks precomputed for $d=128$ (e.g., from Llama or Mistral) **will not work** and will silently increase Mean Squared Error (MSE). You must precompute or use codebooks specifically meant for $d=256$.
2. **K/V Ratio Dynamics**:
   - While Gemma 4 E4B works well with a uniform 3-bit budget (K/V ratio ≈ 1x on global layers), models like Qwen (with K/V ratio > 100x) degrade severely under uniform 3-bit quantization. Always verify the model's K/V ratio before applying bit budgets if adapting the code for other models.
3. **Frontend Architecture**:
   - Keep the frontend as pure static HTML/JS. Do not introduce server-side rendering (e.g., Jinja2 or React SSR). The backend serves APIs only.

---

## 5. Definition of Done for Code Changes

- Passes the 30 checks in `validate_algorithms.py` (if modifying quantizer logic).
- Passes MSE checks against paper bounds.
- Maintains strict adherence to the defined typing and dataclass structures.
- Does not violate the `TurboQuantMSE`-only constraint.
