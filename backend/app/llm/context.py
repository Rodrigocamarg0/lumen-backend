from __future__ import annotations

import json
import logging

from app.config import settings

logger = logging.getLogger("llm.context")


def _loads_object(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        value = json.loads(raw[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


async def summarize_session(
    *,
    previous_summary: str | None,
    user_message: str,
    assistant_message: str,
) -> tuple[str, list[str]]:
    from openai import AsyncOpenAI  # type: ignore[import]

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = (
        "Atualize um resumo curto de uma conversa de estudo espírita. "
        "Preserve objetivos do usuário, dúvidas recorrentes, preferências de resposta e pontos já "
        "explicados. Não transforme preferências do usuário em fatos doutrinários. "
        "Responda somente JSON no formato: "
        '{"summary":"...", "topics":["..."]}.\n\n'
        f"Resumo anterior:\n{previous_summary or '(nenhum)'}\n\n"
        f"Nova mensagem do usuário:\n{user_message}\n\n"
        f"Nova resposta do assistente:\n{assistant_message[:4000]}"
    )
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "Você resume conversas com precisão e concisão."},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=350,
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    data = _loads_object(content)
    summary = str(data.get("summary") or "").strip()
    topics = data.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    return summary[:2000], [str(topic)[:80] for topic in topics[:10]]


async def extract_user_memories(
    *,
    user_message: str,
    assistant_message: str,
) -> list[dict]:
    from openai import AsyncOpenAI  # type: ignore[import]

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = (
        "Extraia apenas memórias úteis e estáveis sobre o usuário para personalizar respostas "
        "futuras. Inclua preferências de idioma, tom, nível de estudo, temas recorrentes e formato "
        "de citação. Não armazene doutrina, fatos gerais, perguntas passageiras, nem dados "
        "sensíveis sem necessidade clara. Responda somente JSON no formato: "
        '{"memories":[{"memory":"...", "topics":["..."], "confidence":0.8}]}.\n\n'
        f"Mensagem do usuário:\n{user_message}\n\n"
        f"Resposta do assistente:\n{assistant_message[:3000]}"
    )
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Você extrai preferências do usuário de forma conservadora.",
            },
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=500,
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    try:
        data = _loads_object(content)
    except Exception:
        logger.exception("Failed to parse memory extraction response")
        return []

    memories = data.get("memories") or []
    if not isinstance(memories, list):
        return []

    normalized = []
    for item in memories[:5]:
        if not isinstance(item, dict):
            continue
        memory = str(item.get("memory") or "").strip()
        if not memory:
            continue
        topics = item.get("topics") or []
        if not isinstance(topics, list):
            topics = []
        confidence = item.get("confidence", 0.5)
        try:
            confidence_value = max(0.0, min(float(confidence), 1.0))
        except (TypeError, ValueError):
            confidence_value = 0.5
        normalized.append(
            {
                "memory": memory[:500],
                "topics": [str(topic)[:80] for topic in topics[:10]],
                "confidence": confidence_value,
            }
        )
    return normalized
