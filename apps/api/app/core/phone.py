"""Phone number normalization built on Google's libphonenumber (``phonenumbers``).

``0888123456``, ``+359888123456``, ``+359 888 123 456`` and ``00359 888 123 456``
all normalize to the same E.164 value ``+359888123456`` with the default BG region.
"""

from __future__ import annotations

from dataclasses import dataclass

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType

_TYPE_NAMES: dict[int, str] = {
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE: "fixed_line",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.TOLL_FREE: "toll_free",
    PhoneNumberType.PREMIUM_RATE: "premium_rate",
    PhoneNumberType.SHARED_COST: "shared_cost",
    PhoneNumberType.PERSONAL_NUMBER: "personal",
    PhoneNumberType.PAGER: "pager",
    PhoneNumberType.UAN: "uan",
    PhoneNumberType.VOICEMAIL: "voicemail",
}

MAX_RAW_LENGTH = 64


@dataclass(frozen=True, slots=True)
class NormalizedPhone:
    raw: str
    e164: str
    national: str
    international: str
    country_code: int
    region: str | None
    phone_type: str


def normalize_phone(raw: str | None, default_region: str = "BG") -> NormalizedPhone | None:
    """Parse and validate a phone number. Returns ``None`` when the input is not a
    valid number (we never store a guessed normalization)."""
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned or len(cleaned) > MAX_RAW_LENGTH:
        return None
    if cleaned.lower().startswith("tel:"):
        cleaned = cleaned[4:]
    # Tolerate common "(0)" trunk notation: +359 (0)888 123 456
    cleaned = cleaned.replace("(0)", "")
    try:
        number = phonenumbers.parse(cleaned, (default_region or "BG").upper())
    except NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    return NormalizedPhone(
        raw=raw.strip(),
        e164=phonenumbers.format_number(number, PhoneNumberFormat.E164),
        national=phonenumbers.format_number(number, PhoneNumberFormat.NATIONAL),
        international=phonenumbers.format_number(number, PhoneNumberFormat.INTERNATIONAL),
        country_code=int(number.country_code or 0),
        region=phonenumbers.region_code_for_number(number),
        phone_type=_TYPE_NAMES.get(phonenumbers.number_type(number), "unknown"),
    )


def same_phone(a: str | None, b: str | None, default_region: str = "BG") -> bool:
    na, nb = normalize_phone(a, default_region), normalize_phone(b, default_region)
    return na is not None and nb is not None and na.e164 == nb.e164


def extract_phones(text: str, default_region: str = "BG", limit: int = 10) -> list[NormalizedPhone]:
    """Find valid phone numbers in free text (e.g. a website's visible text)."""
    found: dict[str, NormalizedPhone] = {}
    if not text:
        return []
    matcher = phonenumbers.PhoneNumberMatcher(
        text[:200_000], (default_region or "BG").upper(), leniency=phonenumbers.Leniency.VALID
    )
    for match in matcher:
        normalized = normalize_phone(match.raw_string, default_region)
        if normalized and normalized.e164 not in found:
            found[normalized.e164] = normalized
            if len(found) >= limit:
                break
    return list(found.values())
