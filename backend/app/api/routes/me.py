from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_current_user
from app.auth.models import AuthenticatedUser

router = APIRouter()


@router.get("/me", response_model=AuthenticatedUser)
def get_me(current_user: Annotated[AuthenticatedUser, Depends(require_current_user)]):
    return current_user
