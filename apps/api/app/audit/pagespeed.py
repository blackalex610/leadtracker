"""Optional Google PageSpeed Insights integration (real Lighthouse data).

Disabled by default; enable in Settings → Website audit and set
PAGESPEED_API_KEY. Runs the mobile strategy only. Failures never fail an audit.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.log import get_logger

log = get_logger(__name__)
PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


async def run_pagespeed(
    url: str, api_key: str, *, timeout_s: float = 60.0, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any] | None:
    params: list[tuple[str, str | int | float | bool | None]] = [
        ("url", url),
        ("strategy", "mobile"),
        ("category", "performance"),
        ("category", "seo"),
        ("category", "accessibility"),
        ("key", api_key),
    ]
    try:
        async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as client:
            response = await client.get(PSI_URL, params=params)
        if response.status_code != 200:
            log.warning("pagespeed_failed", status=response.status_code)
            return None
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("pagespeed_failed", error=type(exc).__name__)
        return None
    categories = (data.get("lighthouseResult") or {}).get("categories") or {}
    audits = (data.get("lighthouseResult") or {}).get("audits") or {}

    def score(name: str) -> int | None:
        value = (categories.get(name) or {}).get("score")
        return round(value * 100) if isinstance(value, int | float) else None

    return {
        "strategy": "mobile",
        "performance": score("performance"),
        "seo": score("seo"),
        "accessibility": score("accessibility"),
        "lcp_ms": (audits.get("largest-contentful-paint") or {}).get("numericValue"),
        "cls": (audits.get("cumulative-layout-shift") or {}).get("numericValue"),
    }
