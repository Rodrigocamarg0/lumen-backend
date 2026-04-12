"""
LLM engine — auto-selects backend based on available hardware:

  • Apple Silicon (MPS)  → mlx-lm   (native Metal, recommended)
  • NVIDIA CUDA          → HuggingFace Transformers + BitsAndBytes 4-bit
  • CPU fallback         → HuggingFace Transformers fp32 (slow, last resort)

Streaming is yielded token-by-token; an async wrapper bridges the sync
MLX/HF generators to FastAPI's async SSE handler.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
import logging
import threading

import torch

logger = logging.getLogger("engine")

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------


def _detect_backend() -> str:
    if torch.backends.mps.is_available():
        return "mlx"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


BACKEND: str = _detect_backend()
logger.info(f"LLM backend: {BACKEND}")

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_tokenizer = None
_model = None
_model_name: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load(model_name: str = "google/gemma-4-E4B-it") -> None:
    """Load model into singletons. No-op if already loaded with same name."""
    global _tokenizer, _model, _model_name

    if _model is not None and _model_name == model_name:
        logger.info("LLM already loaded — skipping")
        return

    if BACKEND == "mlx":
        _load_mlx(model_name)
    elif BACKEND == "cuda":
        _load_cuda(model_name)
    else:
        _load_cpu(model_name)

    _model_name = model_name


def is_loaded() -> bool:
    return _model is not None


def generate(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Blocking generation — returns the full response string."""
    return "".join(stream_tokens(system_prompt, history, user_message, max_new_tokens, temperature))


def stream_tokens(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.7,
) -> Iterator[str]:
    """Yield decoded tokens one at a time."""
    if BACKEND == "mlx":
        yield from _stream_mlx(system_prompt, history, user_message, max_new_tokens, temperature)
    else:
        yield from _stream_hf(system_prompt, history, user_message, max_new_tokens, temperature)


async def astream_tokens(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """Async wrapper — bridges the sync generator to an async event loop."""
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _producer() -> None:
        try:
            for tok in stream_tokens(
                system_prompt, history, user_message, max_new_tokens, temperature
            ):
                loop.call_soon_threadsafe(queue.put_nowait, tok)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_producer, daemon=True).start()

    while True:
        tok = await queue.get()
        if tok is None:
            break
        yield tok


# ---------------------------------------------------------------------------
# MLX backend (Apple Silicon)
# ---------------------------------------------------------------------------


def _mlx_model_id(hf_model_id: str) -> str:
    """
    Map a HuggingFace model ID to the mlx-community 4-bit variant.
    Falls back to the original ID if no mapping is defined.
    """
    _map = {
        "google/gemma-4-E4B-it": "mlx-community/gemma-4-E4B-it-4bit",
        "google/gemma-2-2b-it": "mlx-community/gemma-2-2b-it-4bit",
    }
    return _map.get(hf_model_id, hf_model_id)


def _load_mlx(model_name: str) -> None:
    global _model, _tokenizer
    try:
        from mlx_lm import load as mlx_load  # type: ignore[import]

        mlx_id = _mlx_model_id(model_name)
        logger.info(f"Loading MLX model: {mlx_id}")
        _model, _tokenizer = mlx_load(mlx_id)
        logger.info("MLX model ready")
    except Exception as exc:
        logger.error(f"Failed to load LLM: {exc}")
        raise


def _stream_mlx(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    max_new_tokens: int,
    temperature: float,
) -> Iterator[str]:
    from mlx_lm import stream_generate  # type: ignore[import]
    from mlx_lm.sample_utils import make_sampler  # type: ignore[import]

    prompt = _build_prompt(system_prompt, history, user_message)
    sampler = make_sampler(temperature)
    for chunk in stream_generate(
        _model,
        _tokenizer,
        prompt=prompt,
        max_tokens=max_new_tokens,
        sampler=sampler,
    ):
        yield chunk.text


# ---------------------------------------------------------------------------
# CUDA backend (NVIDIA)
# ---------------------------------------------------------------------------


def _load_cuda(model_name: str) -> None:
    global _model, _tokenizer
    try:
        from transformers import (  # type: ignore[import]
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )

        logger.info(f"Loading tokenizer: {model_name}")
        _tokenizer = AutoTokenizer.from_pretrained(model_name)

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        logger.info(f"Loading model {model_name} in 4-bit …")
        _model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map="auto",
            dtype=torch.bfloat16,
        )
        _model.eval()
        logger.info("CUDA model ready")
    except Exception as exc:
        logger.error(f"Failed to load LLM: {exc}")
        raise


def _stream_hf(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    max_new_tokens: int,
    temperature: float,
) -> Iterator[str]:
    assert _model is not None and _tokenizer is not None
    model, tokenizer = _model, _tokenizer
    from transformers import TextIteratorStreamer  # type: ignore[import]

    input_ids = _build_input_ids_hf(system_prompt, history, user_message)
    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
    gen_kwargs = {
        "input_ids": input_ids,
        "max_new_tokens": max_new_tokens,
        "do_sample": temperature > 0,
        "temperature": temperature if temperature > 0 else None,
        "pad_token_id": tokenizer.eos_token_id,
        "streamer": streamer,
    }
    threading.Thread(target=model.generate, kwargs=gen_kwargs, daemon=True).start()
    for token in streamer:
        if token:
            yield token


# ---------------------------------------------------------------------------
# CPU fallback
# ---------------------------------------------------------------------------


def _load_cpu(model_name: str) -> None:
    global _model, _tokenizer
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore[import]

        logger.warning("No GPU detected — loading model on CPU (slow)")
        _tokenizer = AutoTokenizer.from_pretrained(model_name)
        _model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.float32)
        _model.eval()
        logger.info("CPU model ready")
    except Exception as exc:
        logger.error(f"Failed to load LLM: {exc}")
        raise


# ---------------------------------------------------------------------------
# Prompt building helpers
# ---------------------------------------------------------------------------


def _build_prompt(system_prompt: str, history: list[dict], user_message: str) -> str:
    """Format messages using the tokenizer's chat template → string prompt."""
    assert _tokenizer is not None
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return _tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


def _build_input_ids_hf(system_prompt: str, history: list[dict], user_message: str):
    """HuggingFace tokenised input (CUDA/CPU path)."""
    assert _model is not None and _tokenizer is not None
    prompt = _build_prompt(system_prompt, history, user_message)
    device = next(_model.parameters()).device
    return _tokenizer([prompt], return_tensors="pt").input_ids.to(device)


# ---------------------------------------------------------------------------
# VRAM helpers
# ---------------------------------------------------------------------------


def vram_info() -> tuple[int | None, int | None]:
    """Returns (used_mb, total_mb) or (None, None) if no CUDA device."""
    try:
        if not torch.cuda.is_available():
            return None, None
        used = torch.cuda.memory_allocated(0) // (1024 * 1024)
        total = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
        return used, total
    except Exception:
        return None, None
