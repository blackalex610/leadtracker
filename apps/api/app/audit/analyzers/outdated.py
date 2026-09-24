"""OutdatedAnalyzer: a measurable 'outdated index' (0–100, higher = more outdated).

"Outdated" is never judged by looks. Each point comes from an observable signal
(old copyright, obsolete HTML, no viewport, Flash, HTTP-only, slowness, broken
assets, placeholder content, no modern call-to-action, legacy libraries...).
"""

from __future__ import annotations

from app.audit import keywords as kw
from app.audit.context import AuditContext
from app.audit.signals import OutdatedSignal, Signal


def analyze_outdated(ctx: AuditContext, website_signals: list[Signal]) -> list[OutdatedSignal]:
    codes = {s.code for s in website_signals}
    home = ctx.home
    out: list[OutdatedSignal] = []

    year = ctx.facts.get("copyright_year")
    if isinstance(year, int):
        behind = ctx.today.year - year
        if behind >= 5:
            out.append(OutdatedSignal("old_copyright", "Copyright year 5+ years old", 25, f"© {year}"))
        elif behind >= 3:
            out.append(OutdatedSignal("old_copyright", "Copyright year 3–4 years old", 15, f"© {year}"))
        elif behind == 2:
            out.append(OutdatedSignal("old_copyright", "Copyright year 2 years old", 8, f"© {year}"))

    obsolete_total = sum(home.obsolete_tags.values())
    if obsolete_total:
        tags = ", ".join(f"<{t}>×{n}" for t, n in sorted(home.obsolete_tags.items()))
        out.append(
            OutdatedSignal("obsolete_html", "Obsolete HTML tags", 20 if obsolete_total >= 3 else 10, tags)
        )
    if home.presentational_attrs >= 5:
        out.append(
            OutdatedSignal(
                "presentational_markup",
                "Presentational HTML attributes (bgcolor, width...)",
                5,
                f"{home.presentational_attrs} occurrences",
            )
        )
    if home.doctype and kw.OLD_DOCTYPE_PATTERN.search(home.doctype):
        out.append(OutdatedSignal("old_doctype", "Legacy HTML 4 / XHTML 1.0 doctype", 10))
    if "no_viewport" in codes or "viewport_not_responsive" in codes:
        out.append(OutdatedSignal("non_responsive", "Not built for mobile screens", 20))
    if "table_layout" in codes:
        out.append(OutdatedSignal("table_layout", "Table-based layout", 10))
    if "uses_flash" in codes:
        out.append(OutdatedSignal("flash", "Flash content", 20))
    if "not_https" in codes or "ssl_error" in codes:
        out.append(OutdatedSignal("no_https", "No working HTTPS", 10))
    if "very_slow" in codes:
        out.append(OutdatedSignal("very_slow", "Very slow load", 10))
    elif "slow" in codes:
        out.append(OutdatedSignal("slow", "Slow load", 5))
    if "broken_images" in codes:
        out.append(OutdatedSignal("broken_assets", "Broken images", 5))
    if "broken_links" in codes:
        out.append(OutdatedSignal("dead_links", "Dead internal links", 5))
    if "placeholder_text" in codes:
        out.append(OutdatedSignal("placeholder", "Placeholder content", 10))
    if not ctx.facts.get("cta_detected") and not ctx.facts.get("tel_links"):
        out.append(OutdatedSignal("no_modern_cta", "No modern call-to-action (call/book/contact)", 10))
    jquery = kw.JQUERY_OLD_PATTERN.search(" ".join(home.scripts))
    if jquery:
        out.append(OutdatedSignal("old_jquery", "Legacy jQuery 1.x", 5, f"jQuery {jquery.group(1)}"))
    if kw.IE_CONDITIONAL_PATTERN.search(home.raw_html[:100_000]) or kw.BEST_VIEWED_PATTERN.search(home.text):
        out.append(OutdatedSignal("ie_era", "Internet Explorer-era markup", 5))
    generator = kw.WORDPRESS_GENERATOR.search(home.meta_generator or "")
    if generator and int(generator.group(1)) < 5:
        out.append(
            OutdatedSignal(
                "old_cms", "Old WordPress version", 5, f"WordPress {generator.group(1)}.{generator.group(2)}"
            )
        )
    if "prices_only_in_bgn" in codes:
        out.append(OutdatedSignal("pre_euro_prices", "Prices not updated for the euro", 5))
    return out
