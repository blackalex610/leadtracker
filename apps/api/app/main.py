"""FastAPI application factory."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.api.deps import ensure_default_user
from app.api.routes import admin, calling, data, leads, search, system
from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.log import configure_logging, get_logger, register_secret
from app.providers.base import ProviderError, ProviderNotConfiguredError
from app.providers.registry import close_provider
from app.services.presets import seed_builtin_presets
from app.worker.runner import Worker

log = get_logger("app")

PROVIDER_STATUS_CODES = {
    "provider_not_configured": 503,
    "invalid_api_key": 502,
    "permission_denied": 502,
    "quota_exceeded": 429,
    "rate_limited": 429,
    "provider_unavailable": 503,
    "timeout": 504,
    "network_error": 503,
    "not_found": 404,
    "bad_request": 502,
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        if get_settings().is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api") and request.url.path not in ("/api/health",):
            log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=round((time.perf_counter() - started) * 1000),
            )
        return response


def _error(status_code: int, code: str, message: str, extra: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"detail": {"code": code, "message": message, **(extra or {})}}
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.use_json_logs)
    if settings.provider_api_key:
        register_secret(settings.provider_api_key.get_secret_value())
    if settings.pagespeed_api_key:
        register_secret(settings.pagespeed_api_key.get_secret_value())
    register_secret(settings.secret_key.get_secret_value())
    if settings.is_production and settings.auth_mode == "none":
        log.warning(
            "auth_disabled_in_production",
            message="AUTH_MODE=none: anyone who can reach the API can use it. Put it behind an access proxy.",
        )
    if settings.demo_mode:
        log.warning("demo_mode_enabled", message="DEMO_MODE=true: searches return synthetic businesses.")

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await seed_builtin_presets(session)
        await ensure_default_user(session)

    worker: Worker | None = None
    if settings.run_worker:
        worker = Worker(
            sessionmaker,
            concurrency=settings.worker_concurrency,
            poll_interval=settings.worker_poll_interval_seconds,
        )
        await worker.start()
    app.state.worker = worker
    log.info(
        "api_started",
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        provider_configured=settings.provider_configured,
        auth_mode=settings.auth_mode,
    )
    try:
        yield
    finally:
        if worker is not None:
            await worker.stop()
        await close_provider()
        await dispose_engine()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Lead Tracker API",
        version=settings.app_version,
        description="Local business prospecting: search, audit, score, call, export.",
        lifespan=lifespan if with_lifespan else None,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition", "X-Total-Count"],
    )

    @app.exception_handler(ProviderError)
    async def provider_error_handler(_request: Request, exc: ProviderError) -> JSONResponse:
        status_code = PROVIDER_STATUS_CODES.get(exc.code, 502)
        if not isinstance(exc, ProviderNotConfiguredError):
            log.warning("provider_error", code=exc.code, status=exc.status_code)
        return _error(status_code, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
            )
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()[:20]
        ]
        first = errors[0] if errors else {"msg": "Invalid request", "loc": []}
        where = ".".join(str(p) for p in first["loc"] if p not in ("body", "query"))
        message = f"{where}: {first['msg']}" if where else str(first["msg"])
        return _error(422, "validation_error", message, {"errors": errors})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=type(exc).__name__)
        return _error(500, "internal_error", "Unexpected server error")

    for router in (system.router, search.router, leads.router, calling.router, data.router, admin.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
