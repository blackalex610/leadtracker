"""ASGI entry point for serverless platforms (Vercel: ``api/index.py``).

A configuration error (e.g. a too-short SECRET_KEY) would otherwise crash every
invocation with an opaque platform error page; instead every API request answers
with the list of problems. Values are never echoed, only field names and messages.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError


def _config_error_app(problems: list[str]) -> Any:
    body = json.dumps(
        {"detail": {"code": "setup_required", "message": " ".join(problems), "problems": problems}}
    ).encode()

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return app


def _describe(exc: ValidationError) -> list[str]:
    problems = []
    for error in exc.errors(include_input=False, include_url=False):
        where = ".".join(str(p) for p in error.get("loc", ()))
        message = str(error.get("msg", "invalid value")).removeprefix("Value error, ")
        problems.append(f"{where.upper()}: {message}" if where else message)
    return problems


def build_app() -> Any:
    try:
        from app.config import get_settings

        get_settings()
    except ValidationError as exc:
        return _config_error_app(_describe(exc))
    from app.main import app

    return app


app = build_app()
