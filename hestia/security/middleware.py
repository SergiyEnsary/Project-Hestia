from __future__ import annotations

import logging
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from hestia.security.errors import (
    new_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
            "media-src 'self' blob:; base-uri 'self'; frame-ancestors 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        microphone_policy = "(self)" if request.app.state.config.interfaces.echo.enabled else "()"
        response.headers["Permissions-Policy"] = (
            f"camera=(), microphone={microphone_policy}, geolocation=()"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        try:
            correlation_id = str(uuid.UUID(supplied))
        except ValueError:
            correlation_id = new_correlation_id()
        request.state.correlation_id = correlation_id
        token = set_correlation_id(correlation_id)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled request failure (correlation_id=%s)",
                correlation_id,
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "correlation_id": correlation_id,
                },
            )
        finally:
            reset_correlation_id(token)
        response.headers["X-Request-ID"] = correlation_id
        return response
