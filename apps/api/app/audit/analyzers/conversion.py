"""ConversionAnalyzer: can a visitor call, book, or inquire — and understand the offer?"""

from __future__ import annotations

import re

from app.audit import keywords as kw
from app.audit.context import AuditContext
from app.audit.signals import Signal, make_signal
from app.core.enums import Severity
from app.core.phone import extract_phones, normalize_phone


def _word_match(text: str, words: list[str]) -> str | None:
    for word in words:
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text):
            return word
    return None


def analyze_conversion(ctx: AuditContext) -> list[Signal]:
    signals: list[Signal] = []
    text = ctx.combined_text
    headings = ctx.combined_headings
    link_text = ctx.combined_link_text
    buttons = ctx.combined_buttons
    region = ctx.country_code or "BG"

    # --- phone -------------------------------------------------------------------
    phones: dict[str, str] = {}
    tel_count = 0
    for page in ctx.pages:
        for raw in page.tel_links:
            tel_count += 1
            normalized = normalize_phone(raw, region)
            if normalized:
                phones[normalized.e164] = normalized.international
        for found in extract_phones(page.text, region, limit=5):
            phones.setdefault(found.e164, found.international)
    if not phones and not tel_count:
        signals.append(make_signal("no_phone"))
    elif phones and not tel_count:
        signals.append(make_signal("no_click_to_call"))

    # --- booking ----------------------------------------------------------------
    hrefs = " ".join(
        [link.href.lower() for p in ctx.pages for link in p.links]
        + [s.lower() for p in ctx.pages for s in (*p.scripts, *p.iframes)]
        + [p.raw_html[:200_000].lower() for p in ctx.pages[:1]]
    )
    providers = sorted({d.strip(":/.") for d in kw.BOOKING_PROVIDER_DOMAINS if d in hrefs})
    booking_text = kw.contains_any(link_text + " | " + buttons + " | " + headings, kw.BOOKING_TEXT)
    has_booking = bool(providers or booking_text)
    if not has_booking:
        if ctx.booking_expected:
            signals.append(make_signal("no_booking"))
        else:
            signals.append(
                make_signal("no_booking", "Not expected for this category", penalty=0, severity=Severity.INFO)
            )

    # --- contact CTA --------------------------------------------------------------
    messaging = sorted({m for p in ctx.pages for m in p.messaging_links if m != "mailto"})
    cta_text = kw.contains_any(buttons + " | " + link_text, kw.CTA_TEXT)
    has_cta = bool(tel_count or messaging or has_booking or cta_text)
    if not has_cta:
        signals.append(make_signal("no_contact_cta"))

    # --- contact form -------------------------------------------------------------
    has_form = any(form.looks_like_contact for p in ctx.pages for form in p.forms)
    if not has_form:
        signals.append(make_signal("no_contact_form"))

    # --- services -----------------------------------------------------------------
    services = _word_match(headings + " | " + link_text + " | " + buttons, kw.SERVICE_TEXT)
    if not services:
        signals.append(make_signal("no_clear_service_description"))

    # --- prices -------------------------------------------------------------------
    has_prices = bool(kw.PRICE_PATTERN.search(text)) or bool(
        _word_match(link_text + " | " + headings, kw.PRICE_TEXT)
    )
    if not has_prices:
        signals.append(make_signal("no_price_information"))

    # --- location -----------------------------------------------------------------
    maps = any(
        kw.MAPS_PATTERN.search(u) for p in ctx.pages for u in (*p.iframes, *(link.href for link in p.links))
    )
    has_location = (
        bool(kw.ADDRESS_PATTERN.search(text))
        or maps
        or bool(_word_match(headings + " | " + link_text, kw.LOCATION_TEXT))
    )
    if not has_location:
        signals.append(make_signal("no_location_information"))

    # --- hours --------------------------------------------------------------------
    has_hours = bool(kw.TIME_RANGE_PATTERN.search(text)) or bool(kw.contains_any(text, kw.HOURS_TEXT))
    if not has_hours:
        signals.append(make_signal("no_hours"))

    # --- social -------------------------------------------------------------------
    social: dict[str, str] = {}
    for page in ctx.pages:
        for link in page.links:
            lowered = link.href.lower()
            for network, domains in kw.SOCIAL_DOMAINS.items():
                if network not in social and any(f"{d}/" in lowered or lowered.endswith(d) for d in domains):
                    social[network] = link.href
    if not social:
        signals.append(make_signal("no_social_links"))

    ctx.facts.update(
        {
            "phones_on_site": list(phones.values())[:5],
            "phones_on_site_e164": list(phones.keys())[:5],
            "tel_links": tel_count,
            "messaging_links": messaging,
            "booking_providers": providers,
            "booking_detected": has_booking,
            "booking_text": booking_text,
            "cta_detected": has_cta,
            "contact_form": has_form,
            "services_detected": bool(services),
            "prices_detected": has_prices,
            "location_detected": has_location,
            "hours_detected": has_hours,
            "social_profiles": social,
        }
    )
    return signals
