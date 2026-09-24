"""HTML parsing into a structured page model (selectolax/lexbor: a C,
spec-compliant HTML5 parser; no scripts are executed)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser

from app.audit import keywords as kw

MAX_TEXT_CHARS = 300_000
_WS = re.compile(r"\s+")


@dataclass(slots=True)
class Link:
    href: str
    text: str
    internal: bool


@dataclass(slots=True)
class Form:
    input_types: list[str]
    input_names: list[str]
    has_textarea: bool

    @property
    def looks_like_contact(self) -> bool:
        names = " ".join(self.input_names).lower()
        has_contact_field = (
            "email" in self.input_types
            or "tel" in self.input_types
            or any(
                token in names
                for token in ("email", "mail", "phone", "tel", "name", "имейл", "телефон", "име")
            )
        )
        is_search_only = self.input_types == ["search"] or (
            len(self.input_names) == 1 and self.input_names[0] in ("s", "q", "search")
        )
        return (self.has_textarea or has_contact_field) and not is_search_only


@dataclass(slots=True)
class ParsedPage:
    url: str
    status_code: int
    elapsed_ms: int
    raw_html: str
    title: str | None = None
    meta_description: str | None = None
    meta_viewport: str | None = None
    meta_generator: str | None = None
    lang: str | None = None
    doctype: str | None = None
    h1: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    text: str = ""
    word_count: int = 0
    links: list[Link] = field(default_factory=list)
    tel_links: list[str] = field(default_factory=list)
    messaging_links: list[str] = field(default_factory=list)
    button_texts: list[str] = field(default_factory=list)
    forms: list[Form] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    stylesheets: list[str] = field(default_factory=list)
    iframes: list[str] = field(default_factory=list)
    inline_css: str = ""
    obsolete_tags: dict[str, int] = field(default_factory=dict)
    presentational_attrs: int = 0
    table_count: int = 0
    nested_tables: int = 0
    fixed_width_tables: int = 0
    flash_objects: int = 0
    empty_links: int = 0

    @property
    def https(self) -> bool:
        return self.url.lower().startswith("https://")

    @property
    def lowered_text(self) -> str:
        return self.text.lower()

    def all_link_text(self) -> str:
        return " | ".join(link.text.lower() for link in self.links)


def _clean(value: str | None) -> str:
    return _WS.sub(" ", value or "").strip()


def _attr(node: object, name: str) -> str | None:
    attrs = getattr(node, "attributes", {}) or {}
    value = attrs.get(name)
    return value if isinstance(value, str) else None


def parse_page(url: str, html: str, status_code: int = 200, elapsed_ms: int = 0) -> ParsedPage:
    html = html[: MAX_TEXT_CHARS * 3]
    tree = LexborHTMLParser(html)
    page = ParsedPage(url=url, status_code=status_code, elapsed_ms=elapsed_ms, raw_html=html)

    doctype_match = re.search(r"<!doctype[^>]*>", html[:2000], re.I)
    page.doctype = doctype_match.group(0) if doctype_match else None
    html_node = tree.css_first("html")
    page.lang = _attr(html_node, "lang") if html_node else None

    title_node = tree.css_first("title")
    page.title = _clean(title_node.text()) if title_node else None
    for meta in tree.css("meta"):
        name = (_attr(meta, "name") or _attr(meta, "property") or "").lower()
        content = _attr(meta, "content")
        if name == "description":
            page.meta_description = _clean(content)
        elif name == "viewport":
            page.meta_viewport = _clean(content)
        elif name == "generator":
            page.meta_generator = _clean(content)

    page.h1 = [t for t in (_clean(n.text()) for n in tree.css("h1")) if t]
    page.headings = [t for t in (_clean(n.text()) for n in tree.css("h1, h2, h3")) if t][:100]

    # Structural checks before stripping.
    for tag in kw.OBSOLETE_TAGS:
        count = len(tree.css(tag))
        if count:
            page.obsolete_tags[tag] = count
    page.presentational_attrs = len(
        tree.css("[bgcolor], [background], td[width], table[align], body[text], body[link]")
    )
    tables = tree.css("table")
    page.table_count = len(tables)
    page.nested_tables = len(tree.css("table table"))
    for table in tables:
        width = (_attr(table, "width") or "").strip().rstrip("px")
        if width.isdigit() and int(width) >= 700:
            page.fixed_width_tables += 1
    for node in tree.css("embed, object"):
        src = (_attr(node, "src") or _attr(node, "data") or "").lower()
        typ = (_attr(node, "type") or "").lower()
        if ".swf" in src or "shockwave" in typ:
            page.flash_objects += 1

    page.inline_css = " ".join(n.text() for n in tree.css("style"))[:100_000]

    base = url
    for node in tree.css("a[href]"):
        href = (_attr(node, "href") or "").strip()
        text = _clean(node.text()) or _clean(_attr(node, "title")) or _clean(_attr(node, "aria-label"))
        lowered = href.lower()
        if lowered.startswith("tel:"):
            page.tel_links.append(href[4:])
            continue
        if (
            lowered.startswith(("viber:", "whatsapp:", "sms:"))
            or "wa.me/" in lowered
            or "api.whatsapp.com" in lowered
        ):
            page.messaging_links.append(lowered.split(":")[0])
            continue
        if lowered.startswith("mailto:"):
            # Only the fact that an email link exists is kept, not the address.
            page.messaging_links.append("mailto")
            continue
        if lowered in ("#", "", "javascript:void(0)", "javascript:void(0);", "javascript:;"):
            page.empty_links += 1
            continue
        if lowered.startswith("javascript:"):
            continue
        absolute = urljoin(base, href)
        if urlsplit(absolute).scheme not in ("http", "https"):
            continue
        page.links.append(Link(href=absolute, text=text[:200], internal=_same_host(absolute, url)))
        if len(page.links) >= 500:
            break

    page.button_texts = [
        t
        for t in (
            _clean(n.text()) or _clean(_attr(n, "value"))
            for n in tree.css("button, input[type=submit], input[type=button], .btn, .button")
        )
        if t
    ][:100]

    for form in tree.css("form")[:20]:
        inputs = form.css("input, select")
        page.forms.append(
            Form(
                input_types=[
                    (_attr(i, "type") or "text").lower()
                    for i in inputs
                    if (_attr(i, "type") or "text").lower() not in ("hidden", "submit", "button")
                ],
                input_names=[(_attr(i, "name") or "").lower() for i in inputs if _attr(i, "name")],
                has_textarea=bool(form.css("textarea")),
            )
        )

    page.images = [
        urljoin(base, s)
        for s in (_attr(n, "src") for n in tree.css("img[src]"))
        if s and not s.startswith("data:")
    ][:200]
    page.scripts = [urljoin(base, s) for s in (_attr(n, "src") for n in tree.css("script[src]")) if s][:200]
    page.stylesheets = [
        urljoin(base, s) for s in (_attr(n, "href") for n in tree.css("link[rel=stylesheet][href]")) if s
    ][:100]
    page.iframes = [urljoin(base, s) for s in (_attr(n, "src") for n in tree.css("iframe[src]")) if s][:50]

    for node in tree.css("script, style, noscript, template, svg"):
        node.decompose()
    body = tree.body
    text = _clean(body.text(separator=" ") if body else tree.text(separator=" "))
    page.text = text[:MAX_TEXT_CHARS]
    page.word_count = len(re.findall(r"\w{2,}", page.text))
    return page


def _same_host(a: str, b: str) -> bool:
    ha = (urlsplit(a).hostname or "").lower().removeprefix("www.")
    hb = (urlsplit(b).hostname or "").lower().removeprefix("www.")
    return bool(ha) and ha == hb
