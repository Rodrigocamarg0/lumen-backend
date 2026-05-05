from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import AuthenticatedUser
from app.auth.service import upsert_user
from app.auth.verifier import AuthVerificationError, verify_supabase_token
from app.db.session import get_db_session

bearer_scheme = HTTPBearer(auto_error=False)


def require_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db_session)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        auth_user = verify_supabase_token(credentials.credentials)
    except AuthVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    upsert_user(db, auth_user)
    return auth_user


def require_admin(
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> AuthenticatedUser:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user
