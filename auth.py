"""
Simple API-key authentication middleware for the SSE MCP server.

Key delivery:  Authorization: Bearer <key>   OR   ?api_key=<key>
Disabled when: API_KEY env var is empty (development mode).
Exempt paths:  /health, /  (always pass through)
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_AUTH_WARNING_SHOWN = False
_EXEMPT_PATHS = {"/health", "/"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from config import API_KEY, ENVIRONMENT

        # ── Dev mode: auth disabled ────────────────────────────────────────
        if API_KEY is None:
            global _AUTH_WARNING_SHOWN
            if not _AUTH_WARNING_SHOWN:
                logger.warning(
                    "[WARNING] API_KEY is not set -- authentication DISABLED. "
                    "Set API_KEY in .env before exposing this server publicly."
                )
                _AUTH_WARNING_SHOWN = True
            return await call_next(request)

        # ── Exempt paths ───────────────────────────────────────────────────
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # ── Bearer token ───────────────────────────────────────────────────
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            if auth_header[len("Bearer "):] == API_KEY:
                return await call_next(request)

        # ── Query param ────────────────────────────────────────────────────
        if request.query_params.get("api_key", "") == API_KEY:
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        logger.warning(f"Unauthorized request: {request.method} {request.url.path} from {client}")
        return JSONResponse(
            {
                "error": "Unauthorized",
                "message": (
                    "Valid API key required. "
                    "Pass as 'Authorization: Bearer <key>' header "
                    "or '?api_key=<key>' query parameter."
                ),
            },
            status_code=401,
        )
