from __future__ import annotations

from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    auth_provider: str | None = None
    role: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
