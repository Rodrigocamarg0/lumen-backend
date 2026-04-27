"""
LLM engine for the external OpenAI provider.

RAG retrieval remains local: corpus chunks are embedded, searched with FAISS,
and injected into the system prompt before generation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
import logging

from app.config import settings

logger = logging.getLogger("engine")


def load() -> None:
    """Validate OpenAI runtime configuration. No local model is loaded."""
    if settings.LLM_PROVIDER != "openai":
        raise RuntimeError("Only LLM_PROVIDER=openai is supported")
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set in .env")
    logger.info("OpenAI provider ready — model=%s", settings.OPENAI_MODEL)


def is_loaded() -> bool:
    return settings.LLM_PROVIDER == "openai" and bool(settings.OPENAI_API_KEY)


async def astream_tokens(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.7,
    reasoning_effort: str | None = None,
) -> AsyncIterator[str]:
    from openai import AsyncOpenAI  # type: ignore[import]

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    kwargs: dict = {
        "model": settings.OPENAI_MODEL,
        "messages": messages,
        "max_completion_tokens": max_new_tokens,
        "stream": True,
    }
    effective_reasoning_effort = reasoning_effort
    if effective_reasoning_effort is None:
        effective_reasoning_effort = settings.OPENAI_REASONING_EFFORT
    if effective_reasoning_effort and effective_reasoning_effort != "off":
        kwargs["reasoning_effort"] = effective_reasoning_effort
        kwargs["temperature"] = 1
    else:
        kwargs["temperature"] = temperature

    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token


def vram_info() -> tuple[int | None, int | None]:
    return None, None
