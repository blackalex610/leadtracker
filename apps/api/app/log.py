"""Structured logging (structlog) with secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

_SENSITIVE_KEYS = re.compile(r"(api[_-]?key|token|secret|password|authorization|cookie|x-goog-api-key)", re.I)
_KEY_IN_URL = re.compile(r"([?&](?:key|api_key|token)=)[^&\s]+", re.I)
_secret_values: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a secret so that it is scrubbed from any log output."""
    if value and len(value) >= 6:
        _secret_values.add(value)


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        value = _KEY_IN_URL.sub(r"\1[REDACTED]", value)
        for secret in _secret_values:
            if secret in value:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SENSITIVE_KEYS.search(str(k)) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        if _SENSITIVE_KEYS.search(key):
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = _scrub(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_processor,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[*shared, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=level.upper(), stream=sys.stdout, format="%(levelname)s %(name)s %(message)s")
    # httpx logs full URLs at INFO; keep it quiet so nothing sensitive leaks.
    for noisy in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
