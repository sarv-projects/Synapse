"""Middleware for SYNAPSE v3.0 - Open access, rate limiting, security headers."""
import asyncio
import time
import logging
from collections import defaultdict
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from schema.config import get_settings

logger = logging.getLogger(__name__)

_rate_limiter_instance: "RateLimitMiddleware | None" = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP-based rate limiting — 30 req/min, open access."""

    def __init__(self, app, requests_per_minute: int = 30):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.clients: dict[str, list[float]] = defaultdict(list)
        self.last_pruned = time.time()
        global _rate_limiter_instance
        _rate_limiter_instance = self

    async def start(self):
        """No-op for backward compatibility."""
        pass

    async def stop(self):
        """No-op for backward compatibility."""
        pass

    async def dispatch(self, request: Request, call_next: Callable):
        # Never rate-limit health or docs
        if request.url.path in ("/api/v1/health", "/", "/docs", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Lazily prune expired clients every 5 minutes during requests
        # to avoid memory leaks without running background tasks.
        if now - self.last_pruned > 300:
            self.last_pruned = now
            expired_ips = [ip for ip, reqs in self.clients.items() if not reqs or now - reqs[-1] > 3600]
            for ip in expired_ips:
                self.clients.pop(ip, None)

        # Slide the window
        self.clients[client_ip] = [t for t in self.clients[client_ip] if now - t < 60]

        if len(self.clients[client_ip]) >= self.rpm:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": 60},
            )

        self.clients[client_ip].append(now)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds basic security headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        settings = get_settings()
        response.headers["X-Content-Type-Options"] = settings.x_content_type_options
        response.headers["X-Frame-Options"] = settings.x_frame_options
        response.headers["X-XSS-Protection"] = settings.x_xss_protection
        response.headers["Referrer-Policy"] = settings.referrer_policy
        return response


def add_open_access_middleware(app: FastAPI) -> None:
    """Register all middleware on the FastAPI app."""
    settings = get_settings()

    # CORS — must be added first (outermost layer)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-Api-Key"],
        max_age=86400,
    )

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Rate limiting — 30 RPM per client IP as per SYNAPSE v4.0 spec
    app.add_middleware(RateLimitMiddleware, requests_per_minute=30)
