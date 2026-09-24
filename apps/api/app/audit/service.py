"""WebsiteAuditor: orchestrates fetching and analysis of one business website.

Politeness: robots.txt is honoured, only the homepage plus a few relevant pages
(contact/booking/services/prices/about) are fetched, and asset checks are
capped. A failure never raises — it becomes an audit result with a reason.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.audit import keywords as kw
from app.audit.analyzers.content import analyze_content
from app.audit.analyzers.conversion import analyze_conversion
from app.audit.analyzers.mobile import analyze_mobile
from app.audit.analyzers.outdated import analyze_outdated
from app.audit.analyzers.technical import analyze_technical
from app.audit.analyzers.trust import analyze_trust
from app.audit.context import AuditContext, AuditThresholds
from app.audit.fetcher import FetchError, FetchResult, SafeFetcher
from app.audit.html import ParsedPage, parse_page
from app.audit.pagespeed import run_pagespeed
from app.audit.robots import RobotsPolicy, load_robots
from app.audit.score import calculate_scores
from app.audit.signals import Signal
from app.core.enums import AuditStatus, WebsiteStatus
from app.core.text import normalize_url
from app.log import get_logger

log = get_logger(__name__)

ANALYZER_VERSION = "1.0"
ROBOTS_AGENT = "LeadTrackerAudit"

ERROR_MESSAGES = {
    "dns_failure": "Domain does not resolve (DNS lookup failed)",
    "connection_failed": "Connection to the website failed",
    "timeout": "Connection timeout",
    "ssl_error": "SSL/TLS certificate error",
    "too_many_redirects": "Too many redirects",
    "unsafe_url": "URL points to a non-public address and was not fetched",
    "invalid_url": "Invalid website URL",
    "protocol_error": "The server sent an invalid HTTP response",
    "http_404": "Homepage returns 404 Not Found",
    "http_410": "Homepage returns 410 Gone",
    "http_5xx": "Server error on the homepage",
    "http_error": "Homepage returns an HTTP error",
    "crawler_blocked": "The website blocks automated access (HTTP 401/403/429 or bot challenge)",
    "blocked_by_robots": "robots.txt disallows auditing this site",
    "not_html": "Homepage is not an HTML page",
}

# Errors that say something about the website itself (-> BROKEN_WEBSITE).
BROKEN_CODES = {
    "dns_failure",
    "connection_failed",
    "timeout",
    "ssl_error",
    "too_many_redirects",
    "protocol_error",
    "http_404",
    "http_410",
    "http_5xx",
    "http_error",
    "not_html",
}

PAGE_KEYWORDS = [
    ("contact", [*kw.CONTACT_PAGE_TEXT, "контакти", "kontakti"]),
    ("booking", ["book", "резерв", "запази", "rezerv"]),
    ("services", ["услуги", "services", "uslugi", "процедури", "меню", "menu", "treatments", "classes"]),
    ("prices", ["цени", "ценоразпис", "prices", "pricing", "ceni", "tseni"]),
    ("about", ["за нас", "about", "za-nas", "za nas"]),
]


@dataclass(slots=True)
class AuditOptions:
    timeout_ms: int = 10000
    max_pages: int = 4
    max_response_kb: int = 2048
    respect_robots: bool = True
    slow_threshold_ms: int = 2500
    very_slow_threshold_ms: int = 5000
    check_assets: bool = True
    max_asset_checks: int = 6
    pagespeed_api_key: str | None = None


@dataclass(slots=True)
class AuditResult:
    url: str
    status: AuditStatus
    website_status: WebsiteStatus
    final_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    http_status: int | None = None
    https: bool | None = None
    redirect_chain: list[dict[str, Any]] = field(default_factory=list)
    response_time_ms: int | None = None
    health_score: int | None = None
    outdated_score: int | None = None
    outdated_band: str | None = None
    category_scores: dict[str, Any] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)
    outdated_signals: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    pages: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    analyzer_version: str = ANALYZER_VERSION

    @property
    def signal_codes(self) -> set[str]:
        return {s["code"] for s in self.signals}


def _failure(
    url: str,
    code: str,
    message: str | None = None,
    *,
    http_status: int | None = None,
    redirects: list[dict[str, Any]] | None = None,
    started: datetime | None = None,
) -> AuditResult:
    skipped = code in ("crawler_blocked", "blocked_by_robots", "unsafe_url", "invalid_url")
    return AuditResult(
        url=url,
        status=AuditStatus.SKIPPED if skipped else AuditStatus.FAILED,
        website_status=WebsiteStatus.BROKEN if code in BROKEN_CODES else WebsiteStatus.SKIPPED,
        error_code=code,
        error_message=message or ERROR_MESSAGES.get(code, code),
        http_status=http_status,
        redirect_chain=redirects or [],
        started_at=started or datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )


def _http_error_code(status: int, headers: dict[str, str], body: bytes) -> str:
    lowered = body[:20_000].lower()
    if (
        status in (401, 403, 429)
        or headers.get("cf-mitigated")
        or b"just a moment" in lowered
        or b"captcha" in lowered
    ):
        return "crawler_blocked"
    if status == 503 and (b"cloudflare" in lowered or b"ddos" in lowered):
        return "crawler_blocked"
    if status == 404:
        return "http_404"
    if status == 410:
        return "http_410"
    if status >= 500:
        return "http_5xx"
    return "http_error"


def _with_scheme(url: str, scheme: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((scheme, parts.netloc, parts.path or "/", parts.query, ""))


def select_extra_pages(home: ParsedPage, limit: int) -> list[str]:
    chosen: list[str] = []
    seen = {home.url.rstrip("/")}
    for _label, words in PAGE_KEYWORDS:
        for link in home.links:
            if not link.internal:
                continue
            target = link.href.split("#")[0].rstrip("/")
            if target in seen or not target:
                continue
            haystack = (link.text + " " + urlsplit(link.href).path).lower()
            if any(w in haystack for w in words):
                chosen.append(link.href.split("#")[0])
                seen.add(target)
                break
        if len(chosen) >= limit:
            break
    return chosen


class WebsiteAuditor:
    def __init__(self, fetcher: SafeFetcher, options: AuditOptions) -> None:
        self.fetcher = fetcher
        self.options = options

    async def audit(
        self, url: str, *, booking_expected: bool = False, country_code: str = "BG", today: date | None = None
    ) -> AuditResult:
        started = datetime.now(UTC)
        normalized = normalize_url(url)
        if not normalized:
            return _failure(url, "invalid_url", started=started)
        log.info("website_audit_started", url=normalized)
        try:
            result = await self._audit(
                normalized, booking_expected, country_code, today or date.today(), started
            )
        except Exception as exc:  # defensive: an audit must never crash a job
            log.exception("website_audit_crashed", url=normalized, error=type(exc).__name__)
            result = _failure(
                normalized,
                "connection_failed",
                f"Unexpected audit error ({type(exc).__name__})",
                started=started,
            )
        if result.status == AuditStatus.SUCCESS:
            log.info(
                "website_audit_completed",
                url=normalized,
                health=result.health_score,
                outdated=result.outdated_score,
                ms=result.response_time_ms,
            )
        else:
            log.info("website_audit_failed", url=normalized, code=result.error_code)
        return result

    async def _audit(
        self, url: str, booking_expected: bool, country_code: str, today: date, started: datetime
    ) -> AuditResult:
        opts = self.options
        max_bytes = opts.max_response_kb * 1024

        robots: RobotsPolicy | None = None
        if opts.respect_robots:
            robots = await load_robots(self.fetcher, url, ROBOTS_AGENT)
            if not robots.allows(url):
                return _failure(url, "blocked_by_robots", started=started)

        ssl_error = False
        try:
            home_fetch = await self.fetcher.fetch(url, max_bytes=max_bytes)
        except FetchError as exc:
            if exc.code == "ssl_error" and url.startswith("https://"):
                # Certificate problem: see whether the plain-HTTP site works.
                try:
                    home_fetch = await self.fetcher.fetch(_with_scheme(url, "http"), max_bytes=max_bytes)
                    ssl_error = True
                except FetchError:
                    return _failure(url, "ssl_error", exc.message, started=started)
            else:
                return _failure(url, exc.code, ERROR_MESSAGES.get(exc.code, exc.message), started=started)

        if home_fetch.status_code >= 400:
            code = _http_error_code(home_fetch.status_code, home_fetch.headers, home_fetch.content)
            return _failure(
                url, code, http_status=home_fetch.status_code, redirects=home_fetch.redirects, started=started
            )
        if not home_fetch.is_html:
            return _failure(url, "not_html", http_status=home_fetch.status_code, started=started)

        home = parse_page(
            home_fetch.final_url, home_fetch.text(), home_fetch.status_code, home_fetch.elapsed_ms
        )

        https_available: bool | None = None
        if not home_fetch.https and not ssl_error:
            https_available = await self._https_works(home_fetch.final_url)

        pages = [home]
        page_meta = [self._page_meta(home_fetch, home)]
        for extra_url in select_extra_pages(home, max(0, opts.max_pages - 1)):
            if robots and not robots.allows(extra_url):
                continue
            try:
                fetched = await self.fetcher.fetch(extra_url, max_bytes=max_bytes)
            except FetchError as exc:
                page_meta.append({"url": extra_url, "status": None, "error": exc.code})
                continue
            if fetched.status_code >= 400 or not fetched.is_html:
                page_meta.append({"url": extra_url, "status": fetched.status_code})
                continue
            page = parse_page(fetched.final_url, fetched.text(), fetched.status_code, fetched.elapsed_ms)
            pages.append(page)
            page_meta.append(self._page_meta(fetched, page))

        image_checks: dict[str, int | None] = {}
        link_checks: dict[str, int | None] = {}
        if opts.check_assets and opts.max_asset_checks > 0:
            image_checks, link_checks = await self._check_assets(home, pages, robots)

        ctx = AuditContext(
            listed_url=url,
            home=home,
            pages=pages,
            response_time_ms=home_fetch.total_ms,
            redirect_count=len(home_fetch.redirects),
            final_https=home_fetch.https and not ssl_error,
            https_available=https_available,
            ssl_error=ssl_error,
            image_checks=image_checks,
            link_checks=link_checks,
            booking_expected=booking_expected,
            country_code=country_code,
            today=today,
            thresholds=AuditThresholds(
                slow_ms=opts.slow_threshold_ms, very_slow_ms=opts.very_slow_threshold_ms
            ),
        )
        signals: list[Signal] = []
        signals += analyze_technical(ctx)
        signals += analyze_mobile(ctx)
        signals += analyze_conversion(ctx)
        signals += analyze_content(ctx)
        signals += analyze_trust(ctx)
        outdated_signals = analyze_outdated(ctx, signals)
        scores = calculate_scores(signals, outdated_signals)

        if opts.pagespeed_api_key:
            psi = await run_pagespeed(home_fetch.final_url, opts.pagespeed_api_key)
            if psi:
                ctx.facts["pagespeed"] = psi

        ctx.facts["robots"] = robots.status if robots else "not_checked"
        ctx.facts["effectively_no_site"] = scores.effectively_no_site
        return AuditResult(
            url=url,
            status=AuditStatus.SUCCESS,
            website_status=WebsiteStatus.BROKEN if scores.effectively_no_site else WebsiteStatus.OK,
            final_url=home_fetch.final_url,
            http_status=home_fetch.status_code,
            https=ctx.final_https,
            redirect_chain=home_fetch.redirects,
            response_time_ms=home_fetch.total_ms,
            health_score=scores.health,
            outdated_score=scores.outdated,
            outdated_band=scores.outdated_band,
            category_scores=scores.categories,
            signals=[s.to_dict() for s in signals],
            outdated_signals=[o.to_dict() for o in outdated_signals],
            facts=ctx.facts,
            pages=page_meta,
            started_at=started,
            finished_at=datetime.now(UTC),
        )

    @staticmethod
    def _page_meta(fetched: FetchResult, page: ParsedPage) -> dict[str, Any]:
        return {
            "url": fetched.final_url,
            "status": fetched.status_code,
            "elapsed_ms": fetched.elapsed_ms,
            "title": page.title,
            "words": page.word_count,
            "truncated": fetched.truncated,
        }

    async def _https_works(self, http_url: str) -> bool:
        try:
            result = await self.fetcher.fetch(_with_scheme(http_url, "https"), max_bytes=64 * 1024)
        except FetchError:
            return False
        return result.status_code < 400

    async def _check_assets(
        self, home: ParsedPage, pages: list[ParsedPage], robots: RobotsPolicy | None
    ) -> tuple[dict[str, int | None], dict[str, int | None]]:
        limit = self.options.max_asset_checks
        fetched_pages = {p.url.rstrip("/") for p in pages}
        images = list(dict.fromkeys(home.images))[:limit]
        links = [
            link.href.split("#")[0]
            for link in home.links
            if link.internal
            and link.href.split("#")[0].rstrip("/") not in fetched_pages
            and not link.href.lower().endswith((".pdf", ".jpg", ".png", ".zip", ".doc", ".docx"))
        ]
        links = [u for u in dict.fromkeys(links) if not robots or robots.allows(u)][:limit]
        semaphore = asyncio.Semaphore(3)

        async def check(url: str) -> tuple[str, int | None]:
            async with semaphore:
                return url, await self.fetcher.check(url)

        image_results = await asyncio.gather(*(check(u) for u in images))
        link_results = await asyncio.gather(*(check(u) for u in links))
        return dict(image_results), dict(link_results)
