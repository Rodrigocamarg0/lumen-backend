# Evaluation Suite Specification

> **Purpose:** This document outlines the evaluation strategy and scripts required to validate the Lumen pipeline, ensuring the TurboQuant integration and RAG implementations do not degrade performance or factual accuracy.

---

## 1. Overview

The evaluation suite ensures that any changes to the core algorithms (quantization, RAG retrieval, context caching) strictly maintain the quality of the long-context persona engine. The suite is divided into three primary evaluation scripts.

---

## 2. Evaluation Scripts

### 2.1 `turboquant_eval.py`
**Focus:** Algorithm Correctness and Theoretical Bounds

- **Description:** Validates the quantization distortion against the theoretical limits defined in the TurboQuant paper (arXiv 2504.19874).
- **Checks:**
  - Must pass all 30 standard checks from the `OmarHory/turboquant` bounds suite.
  - Measures MSE distortion vs. the paper's theoretical bounds specifically for $d=256$ (Gemma 4 E4B's `head_dim`).
  - Verifies the inner product error with and without QJL.
- **Pass Criteria:** MSE at 3-bit $\leq 0.035$; MSE at 4-bit $\leq 0.011$ (allowing a 1.2x tolerance over the theoretical d=1536 bounds due to reduced concentration at d=256).

### 2.2 `kv_cache_eval.py`
**Focus:** Memory Compression and Long-Context Integrity

- **Description:** Measures the practical memory savings and the model's ability to retrieve information over extended contexts when using the compressed KV cache.
- **Checks:**
  - **Memory Profiling:** Measures the actual memory footprint of the KV cache over 128K tokens. Target is $\sim 5\times$ compression compared to the FP16 baseline.
  - **Perplexity Degradation:** Evaluates the language modeling perplexity degradation when running at 3.5-bit precision.
  - **Needle-in-a-Haystack (NIHS):** Injects specific facts into the author's corpus context at lengths of 4K, 16K, 64K, and 128K tokens and queries the model.
- **Pass Criteria:** KV compression $\geq 5\times$; PPL degradation $< 1\%$; NIHS recall $> 95\%$ across all context lengths.

### 2.3 `persona_eval.py`
**Focus:** Style Fidelity and RAG Grounding Accuracy

- **Description:** Evaluates the subjective and stylistic quality of the generated responses, as well as the precision of the RAG retrieval mechanism.
- **Checks:**
  - **Style Drift:** Measures n-gram overlap and stylistic perplexity between the generated responses and the author's true corpus over a continuous 50+ turn session.
  - **Retrieval Precision (RAG):** Measures the Recall@10 of the FAISS inner-product search.
  - **Citation Accuracy:** Verifies if the system accurately cites specific known references (e.g., specific numbered questions in *O Livro dos Espíritos*).
- **Pass Criteria:** N-gram style drift $< 5\%$ over 50 turns; RAG Recall@10 $> 0.90$; Citation precision $> 90\%$.

---

## 3. Regression Criteria

**Strict Rule:** Any Pull Request or modification that alters the quantizer implementation, the rotation matrix logic, or the RAG embedding schema **must** include a diff of the metrics from these three evaluation scripts. Code merges are blocked if the metrics degrade beyond the established thresholds.
