from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth.models import AuthenticatedUser
from app.models.conversation import User, utc_now


def upsert_user(db: Session, auth_user: AuthenticatedUser) -> User:
    user = db.get(User, auth_user.id)
    now = utc_now()
    if user is None:
        user = User(
            id=auth_user.id,
            email=str(auth_user.email),
            full_name=auth_user.full_name,
            avatar_url=auth_user.avatar_url,
            auth_provider=auth_user.auth_provider,
            last_seen_at=now,
        )
        db.add(user)
    else:
        user.email = str(auth_user.email)
        user.full_name = auth_user.full_name
        user.avatar_url = auth_user.avatar_url
        user.auth_provider = auth_user.auth_provider
        user.last_seen_at = now
        user.updated_at = now

    db.commit()
    db.refresh(user)
    return user
