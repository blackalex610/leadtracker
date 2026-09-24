"""Text normalization used for de-duplication and keyword matching.

Bulgarian Cyrillic is transliterated with the official Streamlined System so that
"Фитнес Пулс" and "Fitnes Puls" produce the same key.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

_BG_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya",
    # Common non-Bulgarian Cyrillic letters
    "ы": "y", "э": "e", "ё": "yo", "є": "ye", "і": "i", "ї": "yi", "ґ": "g",
}  # fmt: skip

_LEGAL_SUFFIXES = {
    "eood", "ood", "et", "ad", "ead", "sd", "kd", "ltd", "llc", "inc", "gmbh", "srl", "sa", "co",
    "company", "limited", "corp",
}  # fmt: skip

_ADDRESS_STOPWORDS = {
    "ul", "ulitsa", "bul", "bulevard", "blvd", "boulevard", "str", "street", "st", "zhk", "zh", "k",
    "kv", "kvartal", "gr", "grad", "city", "no", "nomer", "bl", "vh", "et", "ap", "bulgaria",
    "balgariya", "republic", "of", "obl", "oblast", "municipality", "obshtina", "pl", "ploshtad",
    "square", "sq", "road", "rd",
}  # fmt: skip

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_POSTAL = re.compile(r"\b\d{4}\b")


def transliterate(value: str) -> str:
    return "".join(_BG_TRANSLIT.get(ch, ch) for ch in value)


def fold(value: str | None) -> str:
    """Lowercase, strip diacritics, transliterate Cyrillic, collapse whitespace."""
    if not value:
        return ""
    lowered = transliterate(value.lower())
    decomposed = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.split())


def name_key(name: str | None) -> str:
    tokens = [t for t in _NON_ALNUM.split(fold(name)) if t]
    meaningful = [t for t in tokens if t not in _LEGAL_SUFFIXES]
    return " ".join(meaningful or tokens)


def address_key(address: str | None, city: str | None = None) -> str | None:
    if not address:
        return None
    folded = fold(address)
    folded = _POSTAL.sub(" ", folded)
    tokens = [t for t in _NON_ALNUM.split(folded) if t and t not in _ADDRESS_STOPWORDS]
    city_tokens = set(_NON_ALNUM.split(fold(city))) if city else set()
    city_tokens |= {"sofia", "sofiya"}
    tokens = [t for t in tokens if t not in city_tokens]
    return " ".join(tokens) or None


# Domains that host profiles for many businesses: never a dedupe signal, and a
# listing that points to one is not the business's own website.
SOCIAL_DOMAINS = {
    "facebook.com", "fb.com", "m.facebook.com", "instagram.com", "tiktok.com", "youtube.com",
    "linkedin.com", "twitter.com", "x.com", "pinterest.com", "vk.com",
}  # fmt: skip
BOOKING_PLATFORM_DOMAINS = {
    "booksy.com", "fresha.com", "treatwell.com", "calendly.com", "simplybook.me", "setmore.com",
    "square.site", "acuityscheduling.com", "mindbodyonline.com", "opentable.com", "thefork.com",
    "glovoapp.com", "foodpanda.bg", "takeaway.com", "wolt.com", "superhosting.bg",
}  # fmt: skip
LINK_HUB_DOMAINS = {"linktr.ee", "linkin.bio", "beacons.ai", "business.site", "sites.google.com", "g.page"}


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    candidate = url.strip()
    if not candidate or any(ch.isspace() for ch in candidate):
        return None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate):
        # "mailto:x", "javascript:..." etc. are not websites; "host:8080/path" is.
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)", candidate):
            return None
        candidate = "http://" + candidate
    try:
        parts = urlsplit(candidate)
        _ = parts.port
    except ValueError:
        return None
    host = parts.hostname or ""
    if parts.scheme.lower() not in ("http", "https") or ("." not in host.strip("[]") and ":" not in host):
        return None
    return candidate


def domain_of(url: str | None) -> str | None:
    normalized = normalize_url(url)
    if not normalized:
        return None
    host = (urlsplit(normalized).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _matches(domain: str, candidates: set[str]) -> bool:
    return any(domain == c or domain.endswith("." + c) for c in candidates)


def website_kind(url: str | None) -> str | None:
    """Classify a listed website: ``own``, ``social``, ``booking_platform`` or ``link_hub``."""
    domain = domain_of(url)
    if not domain:
        return None
    if _matches(domain, SOCIAL_DOMAINS):
        return "social"
    if _matches(domain, BOOKING_PLATFORM_DOMAINS):
        return "booking_platform"
    if _matches(domain, LINK_HUB_DOMAINS):
        return "link_hub"
    return "own"


def dedupe_domain(url: str | None) -> str | None:
    """Domain usable as a de-duplication signal (``None`` for shared platforms)."""
    kind = website_kind(url)
    return domain_of(url) if kind == "own" else None
