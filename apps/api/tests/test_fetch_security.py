"""SSRF protection, fetch limits and auditor failure modes."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.audit.fetcher import FetchError, SafeFetcher
from app.audit.service import AuditOptions, WebsiteAuditor
from app.audit.url_safety import UnsafeURLError, is_public_ip, resolve_public_ips, validate_url_syntax
from app.core.enums import AuditStatus, WebsiteStatus


def resolver_for(mapping: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    async def resolve(host: str, port: int) -> list[str]:
        from app.audit.url_safety import DNSResolutionError

        if host not in mapping:
            raise DNSResolutionError(f"DNS lookup failed for {host}")
        return mapping[host]

    return resolve


def fetcher(
    handler: Callable[[httpx.Request], httpx.Response],
    hosts: dict[str, list[str]] | None = None,
    **kwargs: object,
) -> SafeFetcher:
    return SafeFetcher(
        transport=httpx.MockTransport(handler),
        resolver=resolver_for(hosts or {"example.bg": ["93.184.216.34"]}),
        **kwargs,
    )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "2002:7f00:1::",
        "224.0.0.1",
        "198.18.0.1",
        "192.0.2.10",
        "not-an-ip",
    ],
)
def test_non_public_addresses_are_rejected(ip: str) -> None:
    assert not is_public_ip(ip)


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(ip: str) -> None:
    assert is_public_ip(ip)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://printer.local/",
        "ftp://example.bg/",
        "file:///etc/passwd",
        "http://user:pass@example.bg/",
        "http://example.bg:22/",
        "http://intranet/",
        "gopher://example.bg/",
    ],
)
def test_url_syntax_rejections(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_url_syntax(url)


async def test_hostname_resolving_to_private_address_is_blocked() -> None:
    with pytest.raises(UnsafeURLError):
        await resolve_public_ips(
            "evil.example", 80, resolver_for({"evil.example": ["93.184.216.34", "10.0.0.1"]})
        )


async def test_fetch_connects_to_validated_ip_with_original_host_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, html="<html>ok</html>")

    async with fetcher(handler) as f:
        result = await f.fetch("https://example.bg/page")
    assert result.status_code == 200
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "example.bg"
    assert seen[0].extensions.get("sni_hostname") == "example.bg"


async def test_redirect_to_internal_address_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    async with fetcher(handler) as f:
        with pytest.raises(FetchError) as info:
            await f.fetch("https://example.bg/")
    assert info.value.code == "unsafe_url"


async def test_redirect_to_hostname_that_resolves_privately_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": "http://internal.example.bg/"})

    hosts = {"example.bg": ["93.184.216.34"], "internal.example.bg": ["192.168.0.10"]}
    async with fetcher(handler, hosts) as f:
        with pytest.raises(FetchError) as info:
            await f.fetch("https://example.bg/")
    assert info.value.code == "unsafe_url"


async def test_redirect_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    async with fetcher(handler, max_redirects=3) as f:
        with pytest.raises(FetchError) as info:
            await f.fetch("https://example.bg/")
    assert info.value.code == "too_many_redirects"


async def test_response_size_is_capped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 50_000, headers={"content-type": "text/html"})

    async with fetcher(handler, max_bytes=1000) as f:
        result = await f.fetch("https://example.bg/")
    assert len(result.content) == 1000 and result.truncated


async def test_dns_failure_and_timeouts_are_classified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    async with fetcher(handler) as f:
        with pytest.raises(FetchError) as dns:
            await f.fetch("https://unknown-domain.bg/")
        with pytest.raises(FetchError) as timeout:
            await f.fetch("https://example.bg/")
    assert dns.value.code == "dns_failure"
    assert timeout.value.code == "timeout"


# --- auditor failure modes ----------------------------------------------------------------------


def auditor(handler: Callable[[httpx.Request], httpx.Response], **options: object) -> WebsiteAuditor:
    opts = AuditOptions(check_assets=False, **options)  # type: ignore[arg-type]
    return WebsiteAuditor(fetcher(handler), opts)


HOME = "<html><head><title>Home</title><meta name=viewport content='width=device-width'></head><body><h1>Hi</h1>{}</body></html>"


async def test_robots_disallow_skips_audit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        return httpx.Response(200, html=HOME.format(""))

    result = await auditor(handler).audit("https://example.bg/")
    assert result.status == AuditStatus.SKIPPED
    assert result.error_code == "blocked_by_robots"
    assert result.website_status == WebsiteStatus.SKIPPED


async def test_404_homepage_is_broken() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    result = await auditor(handler).audit("https://example.bg/")
    assert result.status == AuditStatus.FAILED
    assert result.error_code == "http_404"
    assert result.website_status == WebsiteStatus.BROKEN


async def test_403_is_crawler_blocked_not_broken() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403, text="Just a moment...")

    result = await auditor(handler).audit("https://example.bg/")
    assert result.error_code == "crawler_blocked"
    assert result.website_status == WebsiteStatus.SKIPPED


async def test_connection_failure_is_broken_with_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = await auditor(handler).audit("https://example.bg/")
    assert result.website_status == WebsiteStatus.BROKEN
    assert result.error_code == "connection_failed"
    assert result.error_message


async def test_audit_follows_contact_page_and_scores() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/kontakti":
            return httpx.Response(
                200, html="<html><body>Тел: <a href='tel:0888123456'>0888 123 456</a></body></html>"
            )
        return httpx.Response(200, html=HOME.format("<a href='/kontakti'>Контакти</a>"))

    result = await auditor(handler).audit("https://example.bg/")
    assert result.status == AuditStatus.SUCCESS
    assert len(result.pages) == 2
    assert result.facts["phones_on_site_e164"] == ["+359888123456"]
    assert result.health_score is not None and 0 <= result.health_score <= 100
    assert "no_phone" not in result.signal_codes


async def test_invalid_url_is_skipped_safely() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not be called")

    result = await auditor(handler).audit("http://127.0.0.1/admin")
    assert result.status == AuditStatus.SKIPPED
    assert result.error_code == "unsafe_url"
