"""ContentAnalyzer: thin/placeholder/unfinished content, stale copyright, parked pages."""

from __future__ import annotations

from datetime import date

from app.audit import keywords as kw
from app.audit.context import AuditContext
from app.audit.signals import Signal, make_signal

EURO_ADOPTION_BG = date(2026, 1, 1)


def copyright_year(texts: list[str]) -> int | None:
    years: list[int] = []
    for text in texts:
        for match in kw.COPYRIGHT_PATTERN.finditer(text):
            for group in match.groups():
                if group:
                    years.append(int(group))
    plausible = [y for y in years if 1995 <= y <= date.today().year + 1]
    return max(plausible) if plausible else None


def analyze_content(ctx: AuditContext) -> list[Signal]:
    signals: list[Signal] = []
    home = ctx.home
    home_text = home.lowered_text
    title = (home.title or "").lower()
    all_text = ctx.combined_text
    total_words = sum(p.word_count for p in ctx.pages)

    parked = kw.contains_any(title + " " + home_text[:5000], kw.PARKED_PATTERNS)
    default_page = kw.contains_any(title + " " + home_text[:3000], kw.DEFAULT_SERVER_PATTERNS)
    construction = kw.contains_any(title + " " + home_text[:5000], kw.CONSTRUCTION_PATTERNS)

    if parked and home.word_count < 500:
        signals.append(make_signal("parked_domain", f"Found: “{parked}”"))
    elif default_page and home.word_count < 400:
        signals.append(make_signal("default_server_page", f"Found: “{default_page}”"))
    elif construction and home.word_count < 400:
        signals.append(make_signal("under_construction", f"Found: “{construction}”"))

    if home.word_count < 80 and total_words < 200:
        signals.append(make_signal("very_little_text", f"About {home.word_count} words on the homepage"))

    year = copyright_year([p.text for p in ctx.pages])
    if year is not None:
        behind = ctx.today.year - year
        if behind >= 3:
            signals.append(make_signal("outdated_copyright", f"Copyright {year} ({behind} years old)"))
        elif behind == 2:
            signals.append(make_signal("stale_copyright", f"Copyright {year}"))

    placeholder = kw.contains_any(all_text, kw.PLACEHOLDER_PATTERNS)
    if placeholder:
        signals.append(make_signal("placeholder_text", f"Found: “{placeholder}”"))

    generic = kw.contains_any(all_text + " " + title, kw.GENERIC_TEMPLATE_PATTERNS)
    if generic:
        signals.append(make_signal("generic_template_language", f"Found: “{generic}”"))

    if home.empty_links >= 8:
        signals.append(make_signal("unfinished_content", f"{home.empty_links} links point to '#'"))

    if (ctx.country_code or "").upper() == "BG" and ctx.today >= EURO_ADOPTION_BG:
        bgn = kw.BGN_PRICE_PATTERN.search(all_text)
        eur = kw.EUR_PRICE_PATTERN.search(all_text)
        if bgn and not eur:
            signals.append(
                make_signal(
                    "prices_only_in_bgn",
                    f"e.g. “{bgn.group(0)}”; Bulgaria adopted the euro on 1 January 2026",
                )
            )

    ctx.facts.update(
        {
            "word_count": home.word_count,
            "total_word_count": total_words,
            "copyright_year": year,
            "language": home.lang,
        }
    )
    return signals
