from __future__ import annotations

from functools import lru_cache
import logging

import jwt
from jwt import PyJWKClient

from app.auth.models import AuthenticatedUser
from app.config import settings

logger = logging.getLogger("auth.verifier")


class AuthVerificationError(ValueError):
    pass


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.SUPABASE_URL:
        raise AuthVerificationError("SUPABASE_URL is not configured")
    base_url = settings.SUPABASE_URL.rstrip("/")
    return PyJWKClient(f"{base_url}/auth/v1/.well-known/jwks.json")


def _decode_token(token: str) -> dict:
    audience = settings.SUPABASE_JWT_AUDIENCE or None
    issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1" if settings.SUPABASE_URL else None
    options = {"verify_iss": bool(settings.SUPABASE_VERIFY_ISSUER and issuer)}

    if settings.SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience=audience,
                issuer=issuer,
                options=options,
            )
        except jwt.PyJWTError:
            logger.info("Supabase HS256 verification failed; trying JWKS verification")

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "HS256"],
            audience=audience,
            issuer=issuer,
            options=options,
        )
    except jwt.PyJWTError as exc:
        raise AuthVerificationError("Invalid Supabase access token") from exc


def verify_supabase_token(token: str) -> AuthenticatedUser:
    claims = _decode_token(token)
    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        raise AuthVerificationError("Supabase token is missing required identity claims")

    app_metadata = claims.get("app_metadata") or {}
    user_metadata = claims.get("user_metadata") or {}
    full_name = user_metadata.get("full_name") or user_metadata.get("name")

    return AuthenticatedUser(
        id=str(sub),
        email=email,
        full_name=full_name,
        avatar_url=user_metadata.get("avatar_url") or user_metadata.get("picture"),
        auth_provider=app_metadata.get("provider"),
    )
