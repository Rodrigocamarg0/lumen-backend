from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings

logger = logging.getLogger("security")


def add_security_middleware(app: FastAPI, app_settings: Settings) -> None:
    @app.middleware("http")
    async def trace_and_security_headers(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled request error trace_id=%s", trace_id)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "trace_id": trace_id},
                headers={"X-Trace-Id": trace_id},
            )

        response.headers["X-Trace-Id"] = trace_id
        if app_settings.is_production:
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=()",
            )
            response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Trace-Id"],
    )
