from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.conversation import TermsAcceptance, User, utc_now


def record_terms_acceptance(
    db: Session,
    *,
    user_id: str,
    terms_version: str,
    ip: str | None,
    user_agent: str | None,
) -> TermsAcceptance:
    """Insert an append-only audit row and bump the fast-check column on users."""
    acceptance = TermsAcceptance(
        user_id=user_id,
        terms_version=terms_version,
        accepted_at=utc_now(),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(acceptance)

    user = db.get(User, user_id)
    if user is not None:
        user.terms_accepted_version = terms_version

    db.commit()
    db.refresh(acceptance)
    return acceptance
