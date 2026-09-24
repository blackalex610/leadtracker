"""TrustAnalyzer: identity, privacy policy, social proof, about section."""

from __future__ import annotations

from app.audit import keywords as kw
from app.audit.context import AuditContext
from app.audit.signals import Signal, make_signal


def analyze_trust(ctx: AuditContext) -> list[Signal]:
    signals: list[Signal] = []
    link_text = ctx.combined_link_text
    hrefs = " ".join(link.href.lower() for p in ctx.pages for link in p.links)
    headings = ctx.combined_headings
    text = ctx.combined_text

    if (
        not ctx.facts.get("phones_on_site")
        and not ctx.facts.get("tel_links")
        and not ctx.facts.get("location_detected")
    ):
        signals.append(make_signal("no_business_identity"))

    if not (
        kw.contains_any(link_text, kw.PRIVACY_TEXT)
        or kw.contains_any(hrefs, ["privacy", "cookie", "gdpr", "poveritelnost"])
    ):
        signals.append(make_signal("no_privacy_policy"))

    widget = kw.contains_any(" ".join(p.raw_html[:200_000].lower() for p in ctx.pages[:1]), kw.REVIEW_WIDGETS)
    if not (
        kw.contains_any(headings + " | " + link_text, kw.TESTIMONIAL_TEXT)
        or widget
        or kw.contains_any(text, ["отзиви", "testimonials", "what our clients say"])
    ):
        signals.append(make_signal("no_testimonials"))

    if not kw.contains_any(link_text + " | " + headings, kw.ABOUT_TEXT):
        signals.append(make_signal("no_about"))

    return signals
