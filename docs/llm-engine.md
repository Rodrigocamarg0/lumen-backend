# LLM Engine — Backend Reference

> Source of truth for `backend/app/llm/engine.py`.
> Read this before touching anything in `backend/app/llm/`.

---

## Backend auto-detection

The engine detects hardware at import time and selects the appropriate backend:

```
torch.backends.mps.is_available() → True  →  MLX  (Apple Silicon)
torch.cuda.is_available()         → True  →  HF Transformers + BitsAndBytes 4-bit  (NVIDIA)
else                                       →  HF Transformers fp32  (CPU fallback, slow)
```

---

## MLX backend (Apple Silicon)

**Model:** `mlx-community/gemma-4-E4B-it-4bit` (pre-quantized, mapped from `google/gemma-4-E4B-it`)

**Loading:**
```python
from mlx_lm import load as mlx_load
model, tokenizer = mlx_load("mlx-community/gemma-4-E4B-it-4bit")
```

**Streaming — temperature API change (mlx-lm ≥ 0.22):**

The `temp=` and `temperature=` kwargs were removed from `stream_generate()`.
Temperature must now be passed via a sampler object:

```python
from mlx_lm import stream_generate
from mlx_lm.sample_utils import make_sampler

sampler = make_sampler(temperature)   # pass 0.0 for greedy
for chunk in stream_generate(model, tokenizer, prompt=prompt,
                              max_tokens=max_new_tokens, sampler=sampler):
    yield chunk.text
```

**Never** pass `temp=`, `temperature=`, `top_p=`, or `top_k=` directly to `stream_generate()`.
All sampling parameters go through `make_sampler()`.

---

## CUDA backend (NVIDIA)

**Loading with 4-bit BitsAndBytes:**
```python
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=bnb_config,
    device_map="auto",
    dtype=torch.bfloat16,   # use dtype=, NOT torch_dtype= (deprecated)
)
```

**BitsAndBytes is CUDA-only.** Never import or instantiate it on MPS/Apple Silicon — it will crash.

---

## CPU fallback

```python
model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.float32)
```

Log a warning. This is for development only — inference will be very slow.

---

## Singleton pattern

`_model` and `_tokenizer` are module-level singletons initialised to `None`.
Pyright cannot narrow `None` through `assert` on a module-level variable.
Always rebind to a local variable after asserting:

```python
assert _model is not None and _tokenizer is not None
model, tokenizer = _model, _tokenizer   # local rebinding satisfies Pyright
```

---

## Async streaming bridge

`astream_tokens()` bridges the synchronous generator to FastAPI's async SSE handler
using a `threading.Thread` + `asyncio.Queue`. The producer thread calls
`loop.call_soon_threadsafe(queue.put_nowait, tok)` and signals completion with `None`.

---

## Model ID mapping

| HuggingFace ID | MLX community ID |
|---|---|
| `google/gemma-4-E4B-it` | `mlx-community/gemma-4-E4B-it-4bit` |
| `google/gemma-2-2b-it` | `mlx-community/gemma-2-2b-it-4bit` |

If no mapping exists, the original ID is passed to `mlx_lm.load()` unchanged.

---

## See also

- Implementation: `backend/app/llm/engine.py`
- Architecture decisions: `specs/architecture/architecture.md` (ADR-5 — model choice)
- Backend developer guide: `backend/AGENTS.md`
