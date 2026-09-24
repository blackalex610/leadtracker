from __future__ import annotations

import pytest

from app.core.phone import extract_phones, normalize_phone, same_phone
from app.core.text import address_key, dedupe_domain, domain_of, name_key, normalize_url, website_kind


@pytest.mark.parametrize(
    "raw",
    [
        "0888123456",
        "+359888123456",
        "+359 888 123 456",
        "00359 888 123 456",
        "088 812 3456",
        "+359 (0)888 123 456",
        "tel:+359888123456",
        "  0888-123-456  ",
    ],
)
def test_bulgarian_mobile_variants_normalize_to_same_number(raw: str) -> None:
    result = normalize_phone(raw)
    assert result is not None
    assert result.e164 == "+359888123456"
    assert result.country_code == 359
    assert result.region == "BG"
    assert result.phone_type == "mobile"
    assert result.national == "088 812 3456"


def test_sofia_landline() -> None:
    result = normalize_phone("02 987 6543")
    assert result is not None
    assert result.e164 == "+35929876543"
    assert result.phone_type == "fixed_line"


def test_international_number_keeps_its_country() -> None:
    result = normalize_phone("+44 20 7946 0123")
    assert result is not None
    assert result.e164 == "+442079460123"
    assert result.region == "GB"


def test_default_region_is_configurable() -> None:
    result = normalize_phone("020 7946 0123", default_region="GB")
    assert result is not None and result.e164 == "+442079460123"


@pytest.mark.parametrize("raw", ["", None, "12345", "not a phone", "+359 1", "0" * 70])
def test_invalid_numbers_are_rejected(raw: str | None) -> None:
    assert normalize_phone(raw) is None


def test_same_phone() -> None:
    assert same_phone("0888 123 456", "+359888123456")
    assert not same_phone("0888 123 456", "0888 123 457")


def test_extract_phones_from_bulgarian_text() -> None:
    text = "Обадете се на 0888 123 456 или 02/987 65 43. Работно време 09:00-18:00, 2024 г."
    found = [p.e164 for p in extract_phones(text)]
    assert found == ["+359888123456", "+35929876543"]


def test_name_key_transliterates_and_strips_legal_forms() -> None:
    assert name_key("Фитнес Пулс ЕООД") == name_key("Fitnes Puls") == "fitnes puls"
    assert name_key("„Бела Нейлс“ ООД") == "bela neyls"
    assert name_key("Bella Nails Ltd.") == "bella nails"


def test_address_key_ignores_formatting_differences() -> None:
    bg = address_key("ул. „Христо Ботев“ 25, 1000 София, България", "София")
    en = address_key("Hristo Botev St 25, Sofia 1000, Bulgaria", "Sofia")
    assert bg == en == "hristo botev 25"


def test_urls_and_domains() -> None:
    assert normalize_url("example.bg") == "http://example.bg"
    assert normalize_url("ftp://example.bg") is None
    assert normalize_url("javascript:alert(1)") is None
    assert domain_of("https://WWW.Example.BG/path?x=1") == "example.bg"


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://www.facebook.com/bellanails", "social"),
        ("https://instagram.com/bella", "social"),
        ("https://booksy.com/en-us/123_bella", "booking_platform"),
        ("https://www.fresha.com/a/bella", "booking_platform"),
        ("https://linktr.ee/bella", "link_hub"),
        ("https://bella-nails.bg", "own"),
        (None, None),
    ],
)
def test_website_kind(url: str | None, kind: str | None) -> None:
    assert website_kind(url) == kind


def test_shared_platform_domains_are_not_dedupe_signals() -> None:
    assert dedupe_domain("https://facebook.com/a") is None
    assert dedupe_domain("https://www.bella.bg/contact") == "bella.bg"
