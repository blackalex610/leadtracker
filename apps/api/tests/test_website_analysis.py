"""Website signal detection on HTML fixtures (no network)."""

from __future__ import annotations

from datetime import date

from app.audit.analyzers.content import analyze_content, copyright_year
from app.audit.analyzers.conversion import analyze_conversion
from app.audit.analyzers.mobile import analyze_mobile
from app.audit.analyzers.outdated import analyze_outdated
from app.audit.analyzers.technical import analyze_technical
from app.audit.analyzers.trust import analyze_trust
from app.audit.context import AuditContext
from app.audit.html import parse_page
from app.audit.score import calculate_scores
from app.audit.signals import Signal, outdated_band

TODAY = date(2026, 9, 24)

MODERN_BG = """<!DOCTYPE html><html lang="bg"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Студио Бела — маникюр в София</title>
<meta name="description" content="Маникюр и педикюр в центъра на София."></head><body>
<nav><a href="/uslugi">Услуги</a><a href="/ceni">Цени</a><a href="/za-nas">За нас</a><a href="/kontakti">Контакти</a></nav>
<h1>Студио Бела</h1><p>Професионален маникюр, педикюр и грижа за ръцете в сърцето на София. Работим само с
качествени продукти и стерилни инструменти, а екипът ни има дългогодишен опит.</p>
<p>Предлагаме класически и гел маникюр, укрепване на естествения нокът, спа педикюр и терапии за ръце.
Всеки клиент получава индивидуална консултация, а процедурите се извършват в спокойна и уютна обстановка.
Можете да ни посетите след работа, тъй като работим до късно през седмицата.</p>
<a class="btn" href="https://www.fresha.com/a/studio-bela">Запази час</a>
<h2>Отзиви от клиенти</h2><p>„Страхотно обслужване!“</p>
<p>Цени: маникюр 25 €, педикюр 35 €</p>
<p>Адрес: ул. Витоша 15, 1000 София</p><p>Работно време: Пон–Пет 10:00–20:00</p>
<p>Телефон: <a href="tel:+359888123456">0888 123 456</a> <a href="viber://chat?number=359888123456">Viber</a></p>
<form><input name="name"><input type="tel" name="phone"><textarea name="msg"></textarea><button>Изпрати</button></form>
<footer><a href="https://www.instagram.com/studiobela">Instagram</a><a href="/privacy">Политика за поверителност</a>
© 2026 Студио Бела</footer></body></html>"""

OUTDATED = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><title>Fitness Club</title><script src="/js/jquery-1.7.2.min.js"></script>
<!--[if lt IE 8]><link rel="stylesheet" href="ie.css"><![endif]--></head>
<body bgcolor="#000000"><center><table width="980"><tr><td bgcolor="#333"><table><tr><td>
<font size="5">Welcome to our website!</font><font>Lorem ipsum dolor sit amet</font></td></tr></table>
<table><tr><td>Membership: 50 лв на месец. Call 0888 111 222</td></tr></table></td></tr></table>
<embed src="/intro.swf" type="application/x-shockwave-flash">
<a href="#">News</a><a href="#">Gallery</a><a href="#">Team</a><a href="#">Blog</a>
<a href="#">Offers</a><a href="#">Events</a><a href="#">Jobs</a><a href="#">Media</a>
© 2015 Fitness Club</center></body></html>"""


def ctx_for(
    html: str,
    *,
    url: str = "https://studio.bg/",
    booking_expected: bool = True,
    response_ms: int = 800,
    final_https: bool = True,
    extra: list[str] | None = None,
    **kwargs: object,
) -> AuditContext:
    home = parse_page(url, html)
    pages = [home] + [parse_page(url + f"p{i}", h) for i, h in enumerate(extra or [])]
    return AuditContext(
        listed_url=url,
        home=home,
        pages=pages,
        response_time_ms=response_ms,
        redirect_count=0,
        final_https=final_https,
        booking_expected=booking_expected,
        today=TODAY,
        **kwargs,
    )  # type: ignore[arg-type]


def run_all(ctx: AuditContext) -> list[Signal]:
    signals = analyze_technical(ctx) + analyze_mobile(ctx) + analyze_conversion(ctx) + analyze_content(ctx)
    return signals + analyze_trust(ctx)


def codes(signals: list[Signal]) -> set[str]:
    return {s.code for s in signals if s.penalty > 0}


def test_modern_bulgarian_site_has_no_major_problems() -> None:
    ctx = ctx_for(MODERN_BG)
    signals = run_all(ctx)
    assert codes(signals) == set()
    assert ctx.facts["booking_providers"] == ["fresha.com"]
    assert ctx.facts["phones_on_site_e164"] == ["+359888123456"]
    assert "viber" in ctx.facts["messaging_links"]
    assert ctx.facts["social_profiles"]["instagram"].startswith("https://www.instagram.com")
    assert ctx.facts["copyright_year"] == 2026
    scores = calculate_scores(signals, analyze_outdated(ctx, signals))
    assert scores.health == 100
    assert scores.outdated == 0
    assert scores.outdated_band == "Modern / healthy"


def test_outdated_site_signals() -> None:
    ctx = ctx_for(OUTDATED, url="http://club.bg/", final_https=False, response_ms=6200)
    signals = run_all(ctx)
    found = codes(signals)
    for expected in (
        "not_https",
        "very_slow",
        "missing_meta_description",
        "missing_h1",
        "no_viewport",
        "uses_flash",
        "table_layout",
        "no_click_to_call",
        "no_booking",
        "no_contact_cta",
        "no_contact_form",
        "outdated_copyright",
        "placeholder_text",
        "generic_template_language",
        "unfinished_content",
        "prices_only_in_bgn",
        "no_privacy_policy",
        "no_about",
    ):
        assert expected in found, expected
    outdated = analyze_outdated(ctx, signals)
    outdated_codes = {o.code for o in outdated}
    assert {
        "old_copyright",
        "obsolete_html",
        "old_doctype",
        "non_responsive",
        "flash",
        "no_https",
        "very_slow",
        "old_jquery",
        "ie_era",
        "no_modern_cta",
        "pre_euro_prices",
    } <= outdated_codes
    scores = calculate_scores(signals, outdated)
    assert scores.outdated == 100
    assert scores.outdated_band == "Severe problems"
    assert scores.health < 25
    assert scores.categories["mobile"]["score"] == 0


def test_booking_signal_is_informational_when_not_expected() -> None:
    ctx = ctx_for(OUTDATED, booking_expected=False)
    signal = next(s for s in run_all(ctx) if s.code == "no_booking")
    assert signal.penalty == 0 and signal.severity == "info"


def test_parked_and_construction_pages_are_effectively_no_site() -> None:
    parked = ctx_for(
        "<html><head><title>x.bg is for sale</title></head><body>This domain is for sale</body></html>"
    )
    signals = run_all(parked)
    assert "parked_domain" in codes(signals)
    scores = calculate_scores(signals, analyze_outdated(parked, signals))
    assert scores.effectively_no_site and scores.health <= 10

    construction = ctx_for(
        "<html><body><h1>Сайтът е в процес на разработка</h1><p>Очаквайте скоро!</p></body></html>"
    )
    assert "under_construction" in codes(run_all(construction))


def test_http_site_with_working_https_only_gets_redirect_signal() -> None:
    ctx = ctx_for(MODERN_BG, url="http://studio.bg/", final_https=False, https_available=True)
    found = codes(analyze_technical(ctx))
    assert "no_https_redirect" in found and "not_https" not in found


def test_extra_pages_contribute_to_conversion_signals() -> None:
    home = "<html><head><meta name=viewport content='width=device-width'><title>T</title></head><body><h1>T</h1></body></html>"
    contact = "<html><body><h2>Контакти</h2><p>Тел: <a href='tel:029876543'>02 987 6543</a> ул. Шипка 3</p></body></html>"
    ctx = ctx_for(home, extra=[contact])
    found = codes(analyze_conversion(ctx))
    assert "no_phone" not in found
    assert "no_location_information" not in found
    assert ctx.facts["phones_on_site_e164"] == ["+35929876543"]


def test_broken_assets_and_mixed_content() -> None:
    html = "<html><head><title>x</title></head><body><h1>x</h1><img src='http://cdn.bg/a.png'><img src='/b.png'></body></html>"
    ctx = ctx_for(
        html,
        image_checks={"http://cdn.bg/a.png": 200, "https://studio.bg/b.png": 404},
        link_checks={"https://studio.bg/old": None},
    )
    found = codes(analyze_technical(ctx))
    assert {"broken_images", "broken_links", "mixed_content"} <= found


def test_copyright_year_detection() -> None:
    assert copyright_year(["© 2012–2019 Company"]) == 2019
    assert copyright_year(["Всички права запазени 2021"]) == 2021
    assert copyright_year(["Copyright (c) 2008 Foo"]) == 2008
    assert copyright_year(["Open since 1990, call 2024 1234"]) is None


def test_search_form_is_not_a_contact_form() -> None:
    html = "<html><body><form><input type='search' name='s'></form></body></html>"
    assert "no_contact_form" in codes(analyze_conversion(ctx_for(html)))


def test_outdated_bands() -> None:
    assert outdated_band(0) == "Modern / healthy"
    assert outdated_band(25) == "Some issues"
    assert outdated_band(45) == "Needs improvement"
    assert outdated_band(65) == "Clearly outdated"
    assert outdated_band(95) == "Severe problems"


def test_windows_1251_page_decodes() -> None:
    from app.audit.fetcher import decode_body

    html = '<html><head><meta charset="windows-1251"></head><body>Работно време</body></html>'.encode(
        "cp1251"
    )
    assert "Работно време" in decode_body(html, "text/html")
