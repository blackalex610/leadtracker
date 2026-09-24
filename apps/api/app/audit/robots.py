"""robots.txt handling (RFC 9309 semantics, as implemented by major crawlers):
2xx → parse rules; 4xx → no restrictions; 5xx/unreachable → treat as allowed but
note it (the page fetch itself will surface an unreachable site)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.audit.fetcher import FetchError, SafeFetcher

ROBOTS_MAX_BYTES = 256 * 1024


@dataclass(slots=True)
class RobotsPolicy:
    parser: RobotFileParser | None
    status: str  # parsed | missing | unavailable
    agent: str

    def allows(self, url: str) -> bool:
        if self.parser is None:
            return True
        return self.parser.can_fetch(self.agent, url)


async def load_robots(fetcher: SafeFetcher, site_url: str, agent: str) -> RobotsPolicy:
    parts = urlsplit(site_url)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    try:
        result = await fetcher.fetch(robots_url, max_bytes=ROBOTS_MAX_BYTES, accept="text/plain,*/*;q=0.5")
    except FetchError:
        return RobotsPolicy(None, "unavailable", agent)
    if 200 <= result.status_code < 300:
        parser = RobotFileParser()
        parser.parse(result.text().splitlines())
        return RobotsPolicy(parser, "parsed", agent)
    if 400 <= result.status_code < 500:
        return RobotsPolicy(None, "missing", agent)
    return RobotsPolicy(None, "unavailable", agent)
