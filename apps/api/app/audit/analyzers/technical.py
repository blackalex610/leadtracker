"""TechnicalAnalyzer: HTTPS, speed, basic SEO tags, broken assets, redirects."""

from __future__ import annotations

from app.audit.context import AuditContext
from app.audit.signals import Signal, make_signal


def _broken(checks: dict[str, int | None]) -> list[str]:
    return [url for url, status in checks.items() if status is None or status >= 400]


def analyze_technical(ctx: AuditContext) -> list[Signal]:
    signals: list[Signal] = []
    home = ctx.home

    if ctx.ssl_error:
        signals.append(make_signal("ssl_error", "The HTTPS version failed with a certificate/TLS error"))
    elif not ctx.final_https:
        if ctx.https_available:
            signals.append(make_signal("no_https_redirect"))
        else:
            signals.append(make_signal("not_https", "Page loaded over plain HTTP"))

    t = ctx.response_time_ms
    if t >= ctx.thresholds.very_slow_ms:
        signals.append(make_signal("very_slow", f"Homepage took {t / 1000:.1f}s to load"))
    elif t >= ctx.thresholds.slow_ms:
        signals.append(make_signal("slow", f"Homepage took {t / 1000:.1f}s to load"))

    if not home.title:
        signals.append(make_signal("missing_title"))
    if not home.meta_description:
        signals.append(make_signal("missing_meta_description"))
    if not home.h1:
        signals.append(make_signal("missing_h1"))

    broken_images = _broken(ctx.image_checks)
    if broken_images:
        signals.append(
            make_signal(
                "broken_images",
                f"{len(broken_images)} of {len(ctx.image_checks)} checked images failed to load",
            )
        )
    broken_links = _broken(ctx.link_checks)
    if broken_links:
        signals.append(
            make_signal(
                "broken_links",
                f"{len(broken_links)} of {len(ctx.link_checks)} checked internal links are broken",
            )
        )

    if home.https:
        insecure = [
            u
            for u in [*home.scripts, *home.stylesheets, *home.images, *home.iframes]
            if u.lower().startswith("http://")
        ]
        if insecure:
            signals.append(make_signal("mixed_content", f"{len(insecure)} resources loaded over http://"))

    if ctx.redirect_count >= 3:
        signals.append(
            make_signal("excessive_redirects", f"{ctx.redirect_count} redirects before the homepage")
        )

    ctx.facts.update(
        {
            "https": ctx.final_https,
            "response_time_ms": t,
            "redirect_count": ctx.redirect_count,
            "title": home.title,
            "has_meta_description": bool(home.meta_description),
            "generator": home.meta_generator,
            "images_checked": len(ctx.image_checks),
            "broken_images": len(broken_images),
            "links_checked": len(ctx.link_checks),
            "broken_links": len(broken_links),
        }
    )
    return signals
