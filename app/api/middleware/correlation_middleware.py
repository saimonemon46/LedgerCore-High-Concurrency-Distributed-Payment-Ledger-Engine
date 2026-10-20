"""Correlation ID Middleware for LedgerCore.

Extracts or generates an X-Correlation-ID header, binding it to asynchronous
contextvars for distributed trace propagation across logs, outbox events, and brokers.
"""

import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Returns the correlation ID for the active request context."""
    cid = correlation_id_ctx.get()
    return cid if cid else "system"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware extracting or injecting an X-Correlation-ID header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        corr_id = request.headers.get("X-Correlation-ID") or f"cid_{uuid.uuid4().hex}"
        token = correlation_id_ctx.set(corr_id)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = corr_id
            return response
        finally:
            correlation_id_ctx.reset(token)
