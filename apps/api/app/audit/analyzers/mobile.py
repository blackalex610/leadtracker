"""MobileAnalyzer: heuristic detection of *obvious* mobile problems from markup.

This is not a Lighthouse-grade assessment. It flags things that reliably break
mobile rendering (no/fixed viewport, Flash, fixed-width table layouts). Enable
PageSpeed Insights in settings for a measured mobile performance score.
"""

from __future__ import annotations

import re

from app.audit.context import AuditContext
from app.audit.signals import Signal, make_signal

_FIXED_CONTAINER = re.compile(
    r"(?:body|html|#wrap\w*|#container|\.container|#main|#page|\.wrapper|#site)\s*\{[^}]*?(?<![-\w])width\s*:\s*(\d{3,4})px",
    re.I,
)


def analyze_mobile(ctx: AuditContext) -> list[Signal]:
    signals: list[Signal] = []
    home = ctx.home
    viewport = (home.meta_viewport or "").lower().replace(" ", "")

    if not viewport:
        signals.append(make_signal("no_viewport", 'No <meta name="viewport"> tag'))
    elif "width=device-width" not in viewport:
        signals.append(make_signal("viewport_not_responsive", f'viewport="{home.meta_viewport}"'))
    if (
        "user-scalable=no" in viewport
        or "user-scalable=0" in viewport
        or "maximum-scale=1" in viewport.replace(".0", "")
    ):
        signals.append(make_signal("zoom_disabled"))

    if home.flash_objects:
        signals.append(make_signal("uses_flash", f"{home.flash_objects} Flash object(s)"))
    if home.fixed_width_tables or home.nested_tables >= 2:
        signals.append(
            make_signal(
                "table_layout",
                f"{home.table_count} tables, {home.nested_tables} nested, "
                f"{home.fixed_width_tables} with fixed width",
            )
        )
    match = _FIXED_CONTAINER.search(home.inline_css)
    if match and int(match.group(1)) >= 900 and "@media" not in home.inline_css.lower():
        signals.append(make_signal("fixed_width_css", f"Container fixed at {match.group(1)}px"))

    ctx.facts["viewport"] = home.meta_viewport
    return signals
