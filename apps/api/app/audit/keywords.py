"""Keyword dictionaries for website analysis (English, Bulgarian and common
Latin transliterations of Bulgarian). Matching is done on lower-cased text."""

from __future__ import annotations

import re

BOOKING_PROVIDER_DOMAINS = [
    "fresha.com", "shedul.com", "booksy.com", "treatwell", "calendly.com", "simplybook", "setmore.com",
    "acuityscheduling.com", "squareup.com/appointments", "square.site", "mindbodyonline.com", "vagaro.com",
    "gettimely.com", "zenoti.com", "opentable.", "thefork.", "resmio.", "quandoo.", "glofox.com",
    "salonized.com", "noona.", "phorest.com", "appointy.com", "youcanbook.me", "tidycal.com", "://cal.com",
    "reservio.com", "bookero.", "planyo.com", "bookingkit.", "zenchef.", "sevenrooms.com", "tablein.com",
    "ameliabooking", "bookly", "wpbookingcalendar", "latepoint", "reservation-widget", "booking-widget",
]  # fmt: skip

BOOKING_TEXT = [
    "book now", "book online", "book an appointment", "book appointment", "book a table", "book a class",
    "book your", "booking", "reserve", "reservation", "schedule an appointment", "make an appointment",
    "request an appointment", "резервирай", "резервация", "резервации", "запази час", "запазете час",
    "запазване на час", "запиши час", "запишете час", "онлайн записване", "онлайн резервация",
    "запази маса", "резервирайте", "запиши се за", "zapazi chas", "rezervatsiya", "rezervaciya",
    "rezervirai", "rezerviray",
]  # fmt: skip

CTA_TEXT = [
    "contact", "call now", "call us", "call today", "get in touch", "get a quote", "request a quote",
    "free quote", "enquire", "inquire", "message us", "send message", "send a message", "whatsapp",
    "viber", "sign up", "join now", "join today", "free trial", "get started", "order now", "order online",
    "контакт", "свържете се", "свържи се", "обадете се", "обадете ни се", "обади се", "позвънете", "пишете ни",
    "изпратете запитване", "изпрати запитване", "запитване", "поръчай", "поръчайте", "направете заявка",
    "заявка", "безплатна консултация", "консултация", "пробна тренировка", "запиши се", "запишете се",
    "kontakti", "kontakt", "svarzhete se", "obadete se",
]  # fmt: skip

SERVICE_TEXT = [
    "services", "our services", "what we do", "what we offer", "treatments", "menu", "classes", "programs",
    "programmes", "memberships", "procedures", "therapies", "solutions", "packages", "услуги",
    "нашите услуги", "процедури", "меню", "тренировки", "програми", "карти", "абонамент", "абонаменти",
    "какво предлагаме", "терапии", "лечение", "пакети", "обслужване", "uslugi", "proceduri",
]  # fmt: skip

PRICE_TEXT = [
    "price",
    "prices",
    "pricing",
    "price list",
    "rates",
    "цени",
    "ценоразпис",
    "цена",
    "tseni",
    "ceni",
]
PRICE_PATTERN = re.compile(
    r"(\d{1,5}(?:[.,]\d{1,2})?\s?(?:лв\.?|лева|bgn|€|eur\b|евро|euro)|(?:€|\$|£)\s?\d{1,5})", re.I
)
BGN_PRICE_PATTERN = re.compile(r"\d{1,5}(?:[.,]\d{1,2})?\s?(?:лв\.?(?!\w)|лева\b|bgn\b)", re.I)
EUR_PRICE_PATTERN = re.compile(r"(\d{1,5}(?:[.,]\d{1,2})?\s?(?:€|eur\b|евро)|€\s?\d{1,5})", re.I)

LOCATION_TEXT = [
    "address", "our location", "find us", "directions", "how to find us", "адрес", "как да ни намерите",
    "локация", "намерете ни", "местоположение",
]  # fmt: skip
ADDRESS_PATTERN = re.compile(
    r"(\bул\.\s?\S|\bбул\.\s?\S|\bж\.?\s?к\.\s?\S|\bкв\.\s?\S|\bгр\.\s?\S|\bpl\.\s?\S|\bstr\.\s?\S|"
    r"\bstreet\b|\bblvd\b|\bboulevard\b|\bul\.\s?\S|\bbul\.\s?\S|\b\d{4}\s+(?:софия|пловдив|варна|бургас|sofia|plovdiv|varna|burgas)\b)",
    re.I,
)
MAPS_PATTERN = re.compile(
    r"(google\.[a-z.]+/maps|maps\.google\.|goo\.gl/maps|maps\.app\.goo\.gl|openstreetmap)", re.I
)

HOURS_TEXT = [
    "opening hours", "working hours", "business hours", "open hours", "hours", "работно време", "работим",
    "часове", "понеделник", "monday", "mon-fri", "mon – fri", "пон-пет", "пон - пет", "rabotno vreme",
]  # fmt: skip
TIME_RANGE_PATTERN = re.compile(
    r"\b([01]?\d|2[0-3])[:.][0-5]\d\s*(?:ч\.?\s*)?[-–—]\s*([01]?\d|2[0-3])[:.][0-5]\d\b"
)

SOCIAL_DOMAINS = {
    "facebook": ("facebook.com", "fb.com", "fb.me"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "linkedin": ("linkedin.com",),
    "x": ("twitter.com", "x.com"),
    "pinterest": ("pinterest.com",),
}

PRIVACY_TEXT = [
    "privacy", "cookie", "gdpr", "data protection", "поверителност", "лични данни", "бисквитки",
    "защита на данните", "политика за", "общи условия", "terms", "условия за ползване",
]  # fmt: skip
TESTIMONIAL_TEXT = [
    "testimonial", "reviews", "what our clients say", "what our customers say", "client stories",
    "отзиви", "мнения", "препоръки", "клиентите за нас", "казват за нас", "какво казват", "ревюта",
]  # fmt: skip
REVIEW_WIDGETS = ["elfsight", "trustindex", "trustpilot", "reviews-widget", "google-reviews", "birdeye"]
ABOUT_TEXT = [
    "about",
    "about us",
    "our story",
    "our team",
    "team",
    "за нас",
    "кои сме",
    "екип",
    "нашият екип",
    "история",
]
CONTACT_PAGE_TEXT = ["contact", "контакт", "kontakt"]

PLACEHOLDER_PATTERNS = [
    "lorem ipsum", "dolor sit amet", "just another wordpress site", "sample page", "hello world!",
    "this is an example page", "your company name", "company name here", "insert text here",
    "your text here", "add your text", "edit this text", "текст тук", "вашият текст", "примерен текст",
    "примерна страница",
]  # fmt: skip
CONSTRUCTION_PATTERNS = [
    "under construction", "coming soon", "site is under maintenance", "website coming soon",
    "we are working on our website", "в процес на разработка", "в процес на изграждане", "очаквайте скоро",
    "сайтът е в процес", "сайтът се обновява", "в момента обновяваме", "скоро отново",
]  # fmt: skip
PARKED_PATTERNS = [
    "this domain is for sale", "buy this domain", "domain is parked", "parked free", "parkingcrew",
    "sedoparking", "sedo domain parking", "dan.com", "afternic", "hugedomains", "domain for sale",
    "this domain may be for sale", "домейнът е свободен", "този домейн е регистриран", "domain has been registered",
    "this domain has been registered", "is registered with", "web hosting by",
]  # fmt: skip
DEFAULT_SERVER_PATTERNS = [
    "welcome to nginx", "apache2 ubuntu default page", "apache2 debian default page", "it works!",
    "index of /", "test page for the apache", "iis windows server", "default web site page",
    "plesk default page", "web server's default page", "default page for the", "cpanel, inc",
    "this is the default web page",
]  # fmt: skip
GENERIC_TEMPLATE_PATTERNS = [
    "welcome to our website", "welcome to our site", "welcome to my website", "welcome to my blog",
    "proudly powered by wordpress", "site title", "just another", "добре дошли в нашия сайт",
    "добре дошли на нашия сайт", "добре дошли в нашия уебсайт", "добре дошли на нашия уебсайт",
    "добре дошли в сайта",
]  # fmt: skip

COPYRIGHT_PATTERN = re.compile(
    r"(?:©|&copy;|\(c\)|copyright|авторски права|всички права запазени|all rights reserved)"
    r"[^0-9]{0,40}((?:19|20)\d{2})(?:\s*[-–—/]\s*((?:19|20)\d{2}))?",
    re.I,
)

OBSOLETE_TAGS = ["font", "center", "marquee", "blink", "frameset", "frame", "applet", "big", "tt", "strike"]
OLD_DOCTYPE_PATTERN = re.compile(r"<!doctype\s+html\s+public\s+\"-//w3c//dtd\s+(x?html)\s+([\d.]+)", re.I)
IE_CONDITIONAL_PATTERN = re.compile(r"<!--\[if\s+(?:lt|lte|gt|gte)?\s*ie", re.I)
BEST_VIEWED_PATTERN = re.compile(
    r"best viewed (?:in|with)|оптимизиран за internet explorer|internet explorer 6", re.I
)
JQUERY_OLD_PATTERN = re.compile(r"jquery[.-]?(1\.[0-9]+(?:\.[0-9]+)?)(?:\.min)?\.js", re.I)
WORDPRESS_GENERATOR = re.compile(r"wordpress\s+(\d+)\.(\d+)", re.I)


def contains_any(text: str, needles: list[str] | tuple[str, ...]) -> str | None:
    for needle in needles:
        if needle in text:
            return needle
    return None
