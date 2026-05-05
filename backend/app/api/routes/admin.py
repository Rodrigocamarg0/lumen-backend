"""
Admin dashboard endpoints.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.models import (
    AdminMetricPoint,
    AdminStatsResponse,
    AdminTrace,
    AdminTraceMessage,
    AdminTracesResponse,
    PersonaConfigResponse,
    PersonaConfigUpdate,
)
from app.auth.dependencies import require_admin
from app.auth.models import AuthenticatedUser
from app.db.conversations import unix_ts
from app.db.session import get_db_session
from app.models.conversation import (
    ConversationMessage,
    ConversationRun,
    ConversationSession,
    PersonaConfig,
    TermsAcceptance,
    User,
    utc_now,
)
from app.persona.prompts import (
    get_few_shot_examples,
    get_prompt,
    invalidate_persona_config_cache,
    list_registered_persona_ids,
)

router = APIRouter(prefix="/admin")


def _avg(values: list[float | int | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 2)


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(
    _admin: Annotated[AuthenticatedUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db_session)],
) -> AdminStatsResponse:
    now = utc_now()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    window_start = now - timedelta(days=13)

    runs = db.execute(
        select(ConversationRun).where(ConversationRun.created_at >= window_start)
    ).scalars()
    buckets: dict[str, dict[str, list | set | int]] = defaultdict(
        lambda: {
            "users": set(),
            "sessions": set(),
            "runs": 0,
            "tps": [],
            "generation_latency": [],
        }
    )
    for run in runs:
        day = run.created_at.date().isoformat()
        buckets[day]["users"].add(run.user_id)
        buckets[day]["sessions"].add(run.session_id)
        buckets[day]["runs"] += 1
        buckets[day]["tps"].append(run.tokens_per_second)
        buckets[day]["generation_latency"].append(run.generation_latency_ms)

    series = []
    for offset in range(14):
        day = (window_start + timedelta(days=offset)).date().isoformat()
        bucket = buckets[day]
        series.append(
            AdminMetricPoint(
                date=day,
                users=len(bucket["users"]),
                sessions=len(bucket["sessions"]),
                runs=int(bucket["runs"]),
                avg_tokens_per_second=_avg(bucket["tps"]),
                avg_generation_latency_ms=_avg(bucket["generation_latency"]),
            )
        )

    all_runs = db.execute(select(ConversationRun)).scalars().all()
    return AdminStatsResponse(
        total_users=db.scalar(select(func.count()).select_from(User)) or 0,
        daily_active_users=db.scalar(
            select(func.count()).select_from(User).where(User.last_seen_at >= day_ago)
        )
        or 0,
        weekly_active_users=db.scalar(
            select(func.count()).select_from(User).where(User.last_seen_at >= week_ago)
        )
        or 0,
        monthly_active_users=db.scalar(
            select(func.count()).select_from(User).where(User.last_seen_at >= month_ago)
        )
        or 0,
        total_sessions=db.scalar(select(func.count()).select_from(ConversationSession)) or 0,
        active_sessions=db.scalar(
            select(func.count())
            .select_from(ConversationSession)
            .where(ConversationSession.status == "active")
        )
        or 0,
        concurrent_sessions=db.scalar(
            select(func.count())
            .select_from(ConversationSession)
            .where(
                ConversationSession.status == "active",
                ConversationSession.updated_at >= now - timedelta(minutes=15),
            )
        )
        or 0,
        total_interactions=db.scalar(select(func.count()).select_from(ConversationRun)) or 0,
        terms_acceptances=db.scalar(select(func.count()).select_from(TermsAcceptance)) or 0,
        avg_tokens_per_second=_avg([run.tokens_per_second for run in all_runs]),
        avg_rag_latency_ms=_avg([run.rag_latency_ms for run in all_runs]),
        avg_generation_latency_ms=_avg([run.generation_latency_ms for run in all_runs]),
        series=series,
    )


@router.get("/traces", response_model=AdminTracesResponse)
def list_admin_traces(
    _admin: Annotated[AuthenticatedUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    persona: str | None = None,
    model_provider: str | None = None,
    status: str | None = None,
    min_latency_ms: int | None = Query(default=None, ge=0),
    errors_only: bool = False,
) -> AdminTracesResponse:
    filters = []
    if persona:
        filters.append(ConversationRun.persona_id == persona)
    if model_provider:
        filters.append(ConversationRun.model_provider == model_provider)
    if status:
        filters.append(ConversationRun.status == status)
    if min_latency_ms is not None:
        filters.append(ConversationRun.generation_latency_ms >= min_latency_ms)
    if errors_only:
        filters.append(ConversationRun.status != "completed")

    total_stmt = select(func.count()).select_from(ConversationRun)
    stmt = select(ConversationRun)
    if filters:
        total_stmt = total_stmt.where(*filters)
        stmt = stmt.where(*filters)
    total = db.scalar(total_stmt) or 0
    runs = db.execute(
        stmt.order_by(ConversationRun.created_at.desc()).offset(offset).limit(limit)
    ).scalars()

    items = []
    for run in runs:
        message_stmt = (
            select(ConversationMessage)
            .where(
                ConversationMessage.session_id == run.session_id,
                ConversationMessage.created_at <= run.created_at,
            )
            .order_by(ConversationMessage.message_index.desc())
            .limit(2)
        )
        messages = list(reversed(db.execute(message_stmt).scalars().all()))
        items.append(
            AdminTrace(
                id=run.id,
                session_id=run.session_id,
                user_id=run.user_id,
                persona_id=run.persona_id,
                model_provider=run.model_provider,
                model_id=run.model_id,
                status=run.status,
                error_detail=run.error_detail,
                tokens_generated=run.tokens_generated,
                tokens_per_second=run.tokens_per_second,
                rag_latency_ms=run.rag_latency_ms,
                generation_latency_ms=run.generation_latency_ms,
                created_at=unix_ts(run.created_at),
                completed_at=unix_ts(run.completed_at),
                messages=[
                    AdminTraceMessage(
                        role=message.role,
                        content=message.content,
                        citations=message.citations,
                    )
                    for message in messages
                ],
            )
        )

    return AdminTracesResponse(items=items, limit=limit, offset=offset, total=total)


@router.get("/personas", response_model=list[PersonaConfigResponse])
def list_admin_personas(
    _admin: Annotated[AuthenticatedUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db_session)],
) -> list[PersonaConfigResponse]:
    configs = {config.persona_id: config for config in db.execute(select(PersonaConfig)).scalars()}
    responses = []
    for persona_id in list_registered_persona_ids():
        config = configs.get(persona_id)
        responses.append(
            PersonaConfigResponse(
                persona_id=persona_id,
                system_prompt=config.system_prompt if config else get_prompt(persona_id),
                few_shot_examples=(
                    list(config.few_shot_examples or [])
                    if config
                    else get_few_shot_examples(persona_id)
                ),
                updated_at=unix_ts(config.updated_at) if config else 0,
                updated_by=config.updated_by if config else None,
            )
        )
    return responses


@router.put("/personas/{persona_id}", response_model=PersonaConfigResponse)
def update_admin_persona(
    persona_id: str,
    payload: PersonaConfigUpdate,
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db_session)],
) -> PersonaConfigResponse:
    if persona_id not in list_registered_persona_ids():
        raise HTTPException(status_code=404, detail="Unknown persona")

    config = db.get(PersonaConfig, persona_id)
    now = datetime.now(UTC)
    if config is None:
        config = PersonaConfig(persona_id=persona_id)
        db.add(config)
    config.system_prompt = payload.system_prompt
    config.few_shot_examples = payload.few_shot_examples
    config.updated_at = now
    config.updated_by = admin.id
    db.commit()
    db.refresh(config)
    invalidate_persona_config_cache(persona_id)
    return PersonaConfigResponse(
        persona_id=config.persona_id,
        system_prompt=config.system_prompt,
        few_shot_examples=list(config.few_shot_examples or []),
        updated_at=unix_ts(config.updated_at),
        updated_by=config.updated_by,
    )
