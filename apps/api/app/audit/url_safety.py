"""SSRF protection for the website auditor.

Rules:
* only http/https, no embedded credentials, only standard web ports;
* obviously-internal hostnames (localhost, *.local, *.internal, ...) rejected;
* the hostname is resolved and EVERY resolved address must be globally
  routable — loopback, private, link-local (incl. 169.254.169.254 cloud
  metadata), CGNAT, multicast, reserved and unspecified ranges are rejected,
  including IPv4-mapped / 6to4 / Teredo IPv6 encodings;
* the caller connects to the validated IP (pinning), so a second DNS answer
  cannot redirect the request (DNS rebinding);
* every redirect hop is re-validated.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import SplitResult, urlsplit

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, 8080, 8443}
BLOCKED_HOST_SUFFIXES = (
    ".localhost", ".local", ".internal", ".intranet", ".lan", ".home", ".corp", ".localdomain",
    ".home.arpa", ".in-addr.arpa", ".ip6.arpa",
)  # fmt: skip
BLOCKED_HOSTS = {"localhost", "metadata", "metadata.google.internal", "instance-data", "kubernetes.default"}

_EXTRA_BLOCKED_NETWORKS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15",
        "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
        "fc00::/7", "fe80::/10", "ff00::/8", "::/128", "::1/128", "64:ff9b::/96", "100::/64",
    )
]  # fmt: skip

Resolver = Callable[[str, int], Awaitable[list[str]]]


class UnsafeURLError(Exception):
    """The URL must not be fetched."""

    def __init__(self, message: str, code: str = "unsafe_url") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DNSResolutionError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if ip.teredo:
        return ip.teredo[1]
    # IPv4-compatible (deprecated) ::a.b.c.d
    if int(ip) >> 32 == 0 and int(ip) > 1:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def is_public_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    try:
        ip = ipaddress.ip_address(value) if isinstance(value, str) else value
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.scope_id:
            return False
        embedded = _embedded_ipv4(ip)
        if embedded is not None and not is_public_ip(embedded):
            return False
    if any(ip in net for net in _EXTRA_BLOCKED_NETWORKS if net.version == ip.version):
        return False
    return bool(
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def validate_url_syntax(url: str) -> SplitResult:
    if not url or len(url) > 2048:
        raise UnsafeURLError("URL is empty or too long", "invalid_url")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError(f"Malformed URL: {exc}", "invalid_url") from exc
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError("Only http and https URLs can be audited", "invalid_url")
    if parts.username or parts.password or "@" in parts.netloc:
        raise UnsafeURLError("URLs with embedded credentials are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURLError("URL has no host", "invalid_url")
    effective_port = port or (443 if parts.scheme.lower() == "https" else 80)
    if effective_port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"Port {effective_port} is not allowed")
    if host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise UnsafeURLError(f"Host '{host}' is internal")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None and not is_public_ip(literal):
        raise UnsafeURLError("Target address is not publicly routable")
    if literal is None and "." not in host:
        raise UnsafeURLError(f"Host '{host}' is not a public domain name")
    return parts


async def default_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP), timeout=5.0
        )
    except (socket.gaierror, UnicodeError) as exc:
        raise DNSResolutionError(f"DNS lookup failed for {host}") from exc
    except TimeoutError as exc:
        raise DNSResolutionError(f"DNS lookup timed out for {host}") from exc
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


async def resolve_public_ips(host: str, port: int, resolver: Resolver = default_resolver) -> list[str]:
    """Resolve ``host`` and require every address to be public. Returns the
    addresses, IPv4 first."""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    addresses = [str(literal)] if literal is not None else await resolver(host, port)
    if not addresses:
        raise DNSResolutionError(f"No addresses found for {host}")
    for address in addresses:
        if not is_public_ip(address.split("%")[0]):
            raise UnsafeURLError(f"Host '{host}' resolves to a non-public address")
    return sorted(addresses, key=lambda a: ":" in a)
