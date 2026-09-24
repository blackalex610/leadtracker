"""Safe HTTP fetcher for website audits (SSRF-protected, size/time/redirect limited)."""

from __future__ import annotations

import asyncio
import re
import ssl
import time
from dataclasses import dataclass, field
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

import httpx

from app.audit.url_safety import (
    DNSResolutionError,
    Resolver,
    UnsafeURLError,
    default_resolver,
    resolve_public_ips,
    validate_url_syntax,
)

REDIRECT_CODES = {301, 302, 303, 307, 308}
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""", re.I)


class FetchError(Exception):
    """A fetch failed. ``code`` is one of: dns_failure, connection_failed, timeout,
    ssl_error, too_many_redirects, unsafe_url, invalid_url, protocol_error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    truncated: bool
    elapsed_ms: int
    total_ms: int
    redirects: list[dict[str, object]] = field(default_factory=list)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").lower()

    @property
    def is_html(self) -> bool:
        ct = self.content_type
        return not ct or "html" in ct or "xml" in ct

    @property
    def https(self) -> bool:
        return self.final_url.lower().startswith("https://")

    def text(self) -> str:
        return decode_body(self.content, self.headers.get("content-type"))


def decode_body(content: bytes, content_type: str | None) -> str:
    charset = None
    if content_type:
        match = re.search(r"charset=([\w\-]+)", content_type, re.I)
        if match:
            charset = match.group(1)
    if not charset:
        meta = _META_CHARSET.search(content[:4096])
        if meta:
            charset = meta.group(1).decode("ascii", "ignore")
    for candidate in (charset, "utf-8", "windows-1251"):
        if not candidate:
            continue
        try:
            return content.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def _pinned_url(parts: SplitResult, ip: str) -> str:
    host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


def _host_header(parts: SplitResult) -> str:
    host = parts.hostname or ""
    default = 443 if parts.scheme == "https" else 80
    return f"{host}:{parts.port}" if parts.port and parts.port != default else host


class SafeFetcher:
    def __init__(
        self,
        *,
        timeout_ms: int = 10000,
        max_bytes: int = 2 * 1024 * 1024,
        max_redirects: int = 5,
        user_agent: str = "LeadTrackerAudit/1.0",
        resolver: Resolver = default_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout_s = timeout_ms / 1000
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self._resolver = resolver
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_s, connect=min(self.timeout_s, 8.0)),
            follow_redirects=False,
            transport=transport,
            verify=ssl.create_default_context(),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            trust_env=False,  # never route audits through environment proxies
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> SafeFetcher:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def fetch(
        self, url: str, *, method: str = "GET", max_bytes: int | None = None, accept: str | None = None
    ) -> FetchResult:
        try:
            return await asyncio.wait_for(
                self._fetch(url, method=method, max_bytes=max_bytes or self.max_bytes, accept=accept),
                timeout=self.timeout_s * 2 + 2,
            )
        except TimeoutError as exc:
            raise FetchError("timeout", f"Timed out after {self.timeout_s:.0f}s") from exc

    async def _fetch(self, url: str, *, method: str, max_bytes: int, accept: str | None) -> FetchResult:
        started = time.perf_counter()
        current = url
        redirects: list[dict[str, object]] = []
        for _hop in range(self.max_redirects + 1):
            try:
                parts = validate_url_syntax(current)
                port = parts.port or (443 if parts.scheme == "https" else 80)
                ips = await resolve_public_ips(parts.hostname or "", port, self._resolver)
            except UnsafeURLError as exc:
                raise FetchError(exc.code, exc.message) from exc
            except DNSResolutionError as exc:
                raise FetchError("dns_failure", exc.message) from exc

            headers = {
                "Host": _host_header(parts),
                "User-Agent": self.user_agent,
                "Accept": accept or "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                "Accept-Language": "bg,en;q=0.8",
            }
            extensions = {"sni_hostname": parts.hostname} if parts.scheme == "https" else {}
            hop_started = time.perf_counter()
            try:
                request = self._client.build_request(
                    method, _pinned_url(parts, ips[0]), headers=headers, extensions=extensions
                )
                response = await self._client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise FetchError("timeout", f"Timed out connecting to {parts.hostname}") from exc
            except httpx.ConnectError as exc:
                text = str(exc).lower()
                if "ssl" in text or "certificate" in text or isinstance(exc.__cause__, ssl.SSLError):
                    raise FetchError("ssl_error", f"SSL/TLS error for {parts.hostname}: {exc}") from exc
                raise FetchError("connection_failed", f"Could not connect to {parts.hostname}") from exc
            except (httpx.RemoteProtocolError, httpx.LocalProtocolError) as exc:
                raise FetchError("protocol_error", f"Protocol error from {parts.hostname}") from exc
            except httpx.TransportError as exc:
                raise FetchError("connection_failed", f"Connection error for {parts.hostname}") from exc

            try:
                location = response.headers.get("location")
                if response.status_code in REDIRECT_CODES and location:
                    target = urljoin(current, location.strip())
                    redirects.append({"url": current, "status": response.status_code, "location": target})
                    current = target
                    continue
                body = bytearray()
                truncated = False
                if method != "HEAD":
                    try:
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) >= max_bytes:
                                truncated = True
                                del body[max_bytes:]
                                break
                    except httpx.TimeoutException as exc:
                        raise FetchError("timeout", f"Timed out reading {parts.hostname}") from exc
                    except httpx.HTTPError as exc:
                        if not body:
                            raise FetchError("connection_failed", f"Error reading {parts.hostname}") from exc
                        truncated = True
                now = time.perf_counter()
                return FetchResult(
                    requested_url=url,
                    final_url=current,
                    status_code=response.status_code,
                    headers={k.lower(): v for k, v in response.headers.items()},
                    content=bytes(body),
                    truncated=truncated,
                    elapsed_ms=int((now - hop_started) * 1000),
                    total_ms=int((now - started) * 1000),
                    redirects=redirects,
                )
            finally:
                await response.aclose()
        raise FetchError("too_many_redirects", f"More than {self.max_redirects} redirects")

    async def check(self, url: str) -> int | None:
        """Lightweight availability check for assets/links. Returns the status code,
        or ``None`` when the resource could not be fetched at all."""
        try:
            result = await self.fetch(url, method="HEAD", max_bytes=1)
            if result.status_code in (405, 501) or result.status_code >= 400:
                # Some servers reject HEAD; confirm with a tiny GET.
                result = await self.fetch(url, method="GET", max_bytes=1024)
            return result.status_code
        except FetchError:
            return None


def same_site(url_a: str, url_b: str) -> bool:
    host_a = (urlsplit(url_a).hostname or "").lower().removeprefix("www.")
    host_b = (urlsplit(url_b).hostname or "").lower().removeprefix("www.")
    return bool(host_a) and host_a == host_b
