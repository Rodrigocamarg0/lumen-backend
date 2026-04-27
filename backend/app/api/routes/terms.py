"""POST /api/me/terms-acceptance — LGPD-compliant audit endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_current_user
from app.auth.models import AuthenticatedUser
from app.db.session import get_db_session
from app.db.terms import record_terms_acceptance

router = APIRouter()


class AcceptTermsRequest(BaseModel):
    terms_version: str = Field(..., min_length=1, max_length=32)


class AcceptTermsResponse(BaseModel):
    accepted: bool
    terms_version: str
    accepted_at: str


@router.post("/me/terms-acceptance", response_model=AcceptTermsResponse)
def accept_terms(
    body: AcceptTermsRequest,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> AcceptTermsResponse:
    ip = _client_ip(request)
    user_agent = (request.headers.get("user-agent") or "")[:512] or None

    acceptance = record_terms_acceptance(
        db,
        user_id=current_user.id,
        terms_version=body.terms_version,
        ip=ip,
        user_agent=user_agent,
    )

    return AcceptTermsResponse(
        accepted=True,
        terms_version=acceptance.terms_version,
        accepted_at=acceptance.accepted_at.isoformat(),
    )


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    if request.client:
        return str(request.client.host)[:45]
    return None
