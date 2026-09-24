"""Synthetic websites for DEMO_MODE, served for hosts under the reserved
``.demo.invalid`` TLD (which can never resolve on the real internet). Every
other host goes through the normal, SSRF-protected network path."""

from __future__ import annotations

import httpx

from app.audit.url_safety import Resolver, default_resolver

DEMO_SUFFIX = ".demo.invalid"
_DEMO_IP = "93.184.215.14"  # never contacted: requests are answered in-process

_MODERN = """<!DOCTYPE html><html lang="bg"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} — Sofia</title><meta name="description" content="{name} in Sofia. Book online in seconds.">
</head><body><header><nav><a href="/uslugi">Услуги</a><a href="/ceni">Цени</a><a href="/za-nas">За нас</a>
<a href="/kontakti">Контакти</a><a class="btn" href="https://www.fresha.com/demo">Запази час</a></nav></header>
<main><h1>{name}</h1><p>Modern studio in the heart of Sofia with certified specialists and flexible hours.
We focus on quality, hygiene and a friendly atmosphere for every client who visits us.</p>
<h2>Нашите услуги</h2><ul><li>Service one — 25 €</li><li>Service two — 40 €</li><li>Service three — 60 €</li></ul>
<h2>Отзиви</h2><p>“Excellent service, highly recommended.” — a client</p>
<p>Адрес: ул. Демо 1, 1000 София. Работно време: Пон–Пет 09:00–21:00, Съб 10:00–18:00</p>
<p>Телефон: <a href="tel:+442079460100">+44 20 7946 0100</a></p>
<form action="/send"><input type="text" name="name"><input type="email" name="email"><textarea name="msg"></textarea>
<button type="submit">Изпратете запитване</button></form>
<iframe src="https://www.google.com/maps/embed?pb=demo"></iframe></main>
<footer><a href="https://www.facebook.com/demo">Facebook</a> <a href="https://www.instagram.com/demo">Instagram</a>
<a href="/privacy">Политика за поверителност</a> © 2026 {name}</footer>
<img src="/img/hero.jpg" alt="hero"></body></html>"""

_OUTDATED = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"><title>{name}</title>
<script src="/js/jquery-1.4.2.min.js"></script></head>
<body bgcolor="#ffffff"><center><table width="960" border="0"><tr><td bgcolor="#cccccc">
<table><tr><td><font face="Arial" size="4">Добре дошли в нашия сайт!</font></td></tr></table>
<marquee>Промоция!</marquee><font size="2">Ние сме {name}. Предлагаме качествени услуги от 2008 година.
Цена на посещение: 30 лв. Обадете ни се на +44 20 7946 0200.</font>
<img src="/images/banner.gif"><img src="/images/missing.gif"><a href="/old-page.html">Галерия</a>
</td></tr></table>© 2014 {name}. Всички права запазени.</center></body></html>"""

_NO_BOOKING = """<!DOCTYPE html><html lang="bg"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{name}</title></head>
<body><nav><a href="#">Начало</a><a href="/za-nas">За нас</a></nav>
<h1>{name}</h1><p>We are a friendly local team. Visit us in Sofia any time — we are always happy to see new faces
and we take pride in the work we do for our community every single day of the week.</p>
<h2>Услуги</h2><p>Ask us about our services when you visit.</p>
<p>Tel: +44 113 496 0300</p><p>© 2025 {name}</p></body></html>"""

_PARKED = """<!DOCTYPE html><html><head><title>{host} is for sale</title></head>
<body><h1>This domain is for sale</h1><p>Buy this domain today. Parked free courtesy of DemoRegistrar.</p></body></html>"""

_CONSTRUCTION = """<!DOCTYPE html><html lang="bg"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Очаквайте скоро</title></head>
<body><h1>Сайтът е в процес на разработка</h1><p>Очаквайте скоро!</p></body></html>"""

_TEMPLATES = {
    "modern": _MODERN,
    "outdated": _OUTDATED,
    "nobooking": _NO_BOOKING,
    "parked": _PARKED,
    "construction": _CONSTRUCTION,
}


def _name_from_host(host: str) -> str:
    slug = host.split(".")[0]
    return " ".join(part.capitalize() for part in slug.split("-"))


class DemoSiteTransport(httpx.AsyncBaseTransport):
    """Answers demo hosts in-process; delegates everything else."""

    def __init__(self, fallback: httpx.AsyncBaseTransport | None = None) -> None:
        self._fallback = fallback or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.headers.get("host", "").split(":")[0].lower()
        if not host.endswith(DEMO_SUFFIX):
            return await self._fallback.handle_async_request(request)
        variant = host[: -len(DEMO_SUFFIX)].split(".")[-1]
        path = request.url.path
        if variant == "broken":
            raise httpx.ConnectError("Demo: connection refused", request=request)
        if path == "/robots.txt" or path.startswith(("/js/", "/img/", "/images/banner")):
            status = 404 if path == "/robots.txt" else 200
            return httpx.Response(status, content=b"" if request.method == "HEAD" else b"ok", request=request)
        if path.startswith("/images/missing") or path.startswith("/old-page"):
            return httpx.Response(404, content=b"Not found", request=request)
        template = _TEMPLATES.get(variant, _MODERN)
        html = template.format(name=_name_from_host(host), host=host)
        content = b"" if request.method == "HEAD" else html.encode()
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, content=content, request=request
        )

    async def aclose(self) -> None:
        await self._fallback.aclose()


def demo_resolver(fallback: Resolver = default_resolver) -> Resolver:
    async def resolve(host: str, port: int) -> list[str]:
        if host.lower().endswith(DEMO_SUFFIX):
            return [_DEMO_IP]
        return await fallback(host, port)

    return resolve
