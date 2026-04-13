"""
LLM engine — routes to the configured provider:

  LLM_PROVIDER=openai  → OpenAI Chat Completions API (streaming)
  LLM_PROVIDER=local   → auto-selects hardware backend:
    • Apple Silicon (MPS)  → mlx-lm
    • NVIDIA CUDA          → HuggingFace Transformers + BitsAndBytes 4-bit
    • CPU fallback         → HuggingFace Transformers fp32 (slow, last resort)

Streaming is yielded token-by-token; an async wrapper bridges the sync
MLX/HF generators to FastAPI's async SSE handler.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
import logging
import os
import threading

import torch
from transformers import TextIteratorStreamer  # type: ignore[import]

# Reduce CUDA memory fragmentation — must be set before any CUDA allocation.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

from app.cache import TurboQuantCache
from app.cache.kv_cache import patch_model_for_quantized_attention
from app.config import settings

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
_last_kv_cache_metrics: dict[str, object] = {
    "enabled": False,
    "baseline_mb": 0.0,
    "compressed_mb": 0.0,
    "compression_ratio": 1.0,
    "layers_initialized": 0,
    "max_seq_length": 0,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load(model_name: str = "google/gemma-4-E4B-it") -> None:
    """Load model into singletons. No-op for the OpenAI provider."""
    global _tokenizer, _model, _model_name

    if settings.LLM_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set in .env")
        logger.info(f"OpenAI provider — model={settings.OPENAI_MODEL}. No local load needed.")
        return

    if _model is not None and _model_name == model_name:
        logger.info("LLM already loaded — skipping")
        return

    if BACKEND == "cuda":
        vram_mb = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
        if vram_mb <= 6144 and not settings.USE_TURBOQUANT_CACHE:
            logger.warning(
                f"VRAM={vram_mb}MB — TurboQuant KV cache is strongly recommended on this "
                "GPU. Set USE_TURBOQUANT_CACHE=true in .env to reduce KV cache VRAM usage."
            )

    if BACKEND == "mlx":
        _load_mlx(model_name)
    elif BACKEND == "cuda":
        _load_cuda(model_name)
    else:
        _load_cpu(model_name)

    _model_name = model_name


def is_loaded() -> bool:
    if settings.LLM_PROVIDER == "openai":
        return bool(settings.OPENAI_API_KEY)
    return _model is not None


def kv_cache_metrics() -> dict[str, object]:
    return dict(_last_kv_cache_metrics)


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
    """Async token stream — routes to OpenAI or local backend."""
    if settings.LLM_PROVIDER == "openai":
        async for tok in _astream_openai(
            system_prompt, history, user_message, max_new_tokens, temperature
        ):
            yield tok
        return

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
# OpenAI backend
# ---------------------------------------------------------------------------


async def _astream_openai(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    max_new_tokens: int,
    temperature: float,
) -> AsyncIterator[str]:
    from openai import AsyncOpenAI  # type: ignore[import]

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    stream = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        max_completion_tokens=max_new_tokens,
        temperature=temperature,
        stream=True,
    )
    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token


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
        logger.error(f"Failed to load MLX model: {exc}")
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

        # GTX 1650 / Turing (CC 7.5) has poor BF16 throughput — use FP16.
        # Ampere+ (CC 8.0+) can switch back to bfloat16 for better stability.
        compute_dtype = (
            torch.bfloat16 if torch.cuda.get_device_capability(0)[0] >= 8 else torch.float16
        )
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            llm_int8_enable_fp32_cpu_offload=True,
        )
        # Force all layers onto the GPU when the model fits in VRAM.
        # device_map="auto" is too conservative — it spills layers to CPU
        # even when there is room, which kills throughput on small cards.
        vram_free = torch.cuda.mem_get_info(0)[0] // (1024 * 1024)
        device_map = "cuda" if vram_free >= settings.MIN_VRAM_MB_FOR_GPU_ONLY else "auto"
        logger.info(
            f"Loading model {model_name} in 4-bit "
            f"(compute_dtype={compute_dtype}, device_map={device_map!r}, "
            f"free_vram={vram_free}MB) …"
        )
        _model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map=device_map,
            dtype=compute_dtype,
            offload_buffers=True,
        )
        device_map_used = getattr(_model, "hf_device_map", {})
        cpu_layers = [k for k, v in device_map_used.items() if str(v) == "cpu"]
        if cpu_layers:
            logger.warning(
                f"{len(cpu_layers)} layers on CPU — inference will be slow: {cpu_layers[:5]}"
            )
        else:
            logger.info("All layers on GPU")
        if settings.USE_TURBOQUANT_CACHE:
            try:
                patch_model_for_quantized_attention(_model)
                logger.info("TurboQuant KV cache patching applied")
            except RuntimeError as exc:
                logger.warning(
                    f"TurboQuant KV cache disabled — architecture not supported "
                    f"({model_name}): {exc}. Falling back to standard KV cache."
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

    input_ids, attention_mask = _build_input_ids_hf(system_prompt, history, user_message)
    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
    cache = None
    gen_kwargs = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "max_new_tokens": max_new_tokens,
        "do_sample": temperature > 0,
        "temperature": temperature if temperature > 0 else None,
        "pad_token_id": tokenizer.eos_token_id,
        "streamer": streamer,
    }
    if settings.USE_TURBOQUANT_CACHE:
        cache = TurboQuantCache(
            bits=settings.KV_CACHE_BITS,
            outlier_threshold=settings.KV_CACHE_OUTLIER_THRESHOLD,
            num_hidden_layers=getattr(model.config, "num_hidden_layers", None),
        )
        gen_kwargs["past_key_values"] = cache

    def _run_generation() -> None:
        global _last_kv_cache_metrics
        try:
            model.generate(**gen_kwargs)
        finally:
            if cache is not None:
                _last_kv_cache_metrics = {"enabled": True, **cache.memory_stats()}
            else:
                _last_kv_cache_metrics = {
                    "enabled": False,
                    "baseline_mb": 0.0,
                    "compressed_mb": 0.0,
                    "compression_ratio": 1.0,
                    "layers_initialized": 0,
                    "max_seq_length": 0,
                }

    worker = threading.Thread(target=_run_generation, daemon=True)
    worker.start()
    for token in streamer:
        if token:
            yield token
    worker.join()


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
        if settings.USE_TURBOQUANT_CACHE:
            patch_model_for_quantized_attention(_model)
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


def _build_input_ids_hf(system_prompt: str, history: list[dict], user_message: str) -> tuple:
    """HuggingFace tokenised input (CUDA/CPU path). Returns (input_ids, attention_mask)."""
    assert _model is not None and _tokenizer is not None
    prompt = _build_prompt(system_prompt, history, user_message)
    device = next(_model.parameters()).device
    encoded = _tokenizer([prompt], return_tensors="pt")
    return encoded.input_ids.to(device), encoded.attention_mask.to(device)


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
