from __future__ import annotations

from app.audit.demo_sites import DemoSiteTransport, demo_resolver
from app.audit.fetcher import SafeFetcher
from app.audit.service import AuditOptions, WebsiteAuditor
from app.config import get_settings
from app.services.settings import AuditSettings


def audit_options(audit: AuditSettings) -> AuditOptions:
    settings = get_settings()
    psi_key = settings.pagespeed_api_key.get_secret_value() if settings.pagespeed_api_key else None
    return AuditOptions(
        timeout_ms=audit.timeout_ms,
        max_pages=audit.max_pages,
        max_response_kb=audit.max_response_kb,
        respect_robots=audit.respect_robots,
        slow_threshold_ms=audit.slow_threshold_ms,
        very_slow_threshold_ms=audit.very_slow_threshold_ms,
        check_assets=audit.check_assets,
        max_asset_checks=audit.max_asset_checks,
        pagespeed_api_key=psi_key if audit.pagespeed_enabled else None,
    )


def build_fetcher(audit: AuditSettings) -> SafeFetcher:
    settings = get_settings()
    kwargs: dict[str, object] = {}
    if settings.demo_mode:
        kwargs = {"transport": DemoSiteTransport(), "resolver": demo_resolver()}
    return SafeFetcher(
        timeout_ms=audit.timeout_ms,
        max_bytes=audit.max_response_kb * 1024,
        user_agent=settings.audit_user_agent,
        **kwargs,  # type: ignore[arg-type]
    )


def build_auditor(audit: AuditSettings) -> WebsiteAuditor:
    return WebsiteAuditor(build_fetcher(audit), audit_options(audit))
