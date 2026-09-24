"""Deterministic pitch builder. Every sentence about the business is backed by an
observed signal; nothing is invented. Output is a short opener the salesperson
can adapt, plus the verified talking points it was built from."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import OpportunityType
from app.core.text import domain_of
from app.scoring.engine import ScoreResult
from app.scoring.inputs import ScoringInput

PITCH_ORDER = [
    OpportunityType.NO_WEBSITE,
    OpportunityType.BROKEN_WEBSITE,
    OpportunityType.NO_BOOKING,
    OpportunityType.MOBILE_PROBLEM,
    OpportunityType.WEBSITE_REDESIGN,
    OpportunityType.OUTDATED_WEBSITE,
    OpportunityType.NO_CONTACT_CTA,
    OpportunityType.WEAK_CONVERSION,
    OpportunityType.SLOW_WEBSITE,
    OpportunityType.MISSING_BUSINESS_INFO,
    OpportunityType.GOOGLE_PROFILE,
    OpportunityType.LOW_REVIEWS,
]

CITY_BG = {
    "sofia": "София",
    "plovdiv": "Пловдив",
    "varna": "Варна",
    "burgas": "Бургас",
    "ruse": "Русе",
    "stara zagora": "Стара Загора",
    "pleven": "Плевен",
    "veliko tarnovo": "Велико Търново",
}

MISSING_BG = {
    "phone number": "телефон", "contact call-to-action": "бутон за контакт", "online booking": "онлайн резервация",
    "contact form": "форма за контакт", "services section": "описание на услугите", "prices": "цени",
    "address/location": "адрес", "opening hours": "работно време",
}  # fmt: skip
GOOGLE_MISSING = {
    "missing_hours": ("opening hours", "работно време"),
    "missing_phone": ("a phone number", "телефон"),
    "missing_address": ("an address", "адрес"),
    "few_photos": ("photos", "снимки"),
    "missing_description": ("a description", "описание"),
}


@dataclass(slots=True)
class Pitch:
    language: str
    text: str
    primary_opportunity: str | None
    talking_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "text": self.text,
            "primary_opportunity": self.primary_opportunity,
            "talking_points": self.talking_points,
        }


def _join(items: list[str], conj: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {conj} " + items[-1]


def _category_phrase(inp: ScoringInput, lang: str) -> str:
    if inp.niche:
        if lang == "bg":
            return inp.niche.label_bg or "местни бизнеси"
        return inp.niche.label.lower()
    return "местни бизнеси" if lang == "bg" else "local businesses"


def _top_issues(result: ScoreResult, inp: ScoringInput, n: int = 2) -> list[str]:
    if not inp.audit:
        return []
    ranked = sorted(
        (s for s in inp.audit.signals if (s.get("penalty") or 0) > 0), key=lambda s: -int(s["penalty"])
    )
    return [str(s["label"]).lower() for s in ranked[:n]]


def build_pitch(inp: ScoringInput, result: ScoreResult, language: str = "en") -> Pitch:
    lang = "bg" if language == "bg" else "en"
    primary = next((o for o in PITCH_ORDER if o in result.opportunities), None)
    city = inp.city or ("София" if lang == "bg" else "Sofia")
    if lang == "bg":
        city = CITY_BG.get(city.lower(), city)
    category = _category_phrase(inp, lang)
    audit = inp.audit
    parts: list[str] = []

    if lang == "en":
        parts.append(f"Hi, I came across {inp.name} while looking at {category} in {city}.")
        if inp.review_count and inp.review_count >= 50:
            rating = f" and a {inp.rating:.1f}★ rating" if inp.rating and inp.rating >= 4.5 else ""
            parts.append(
                f"You have {inp.review_count} Google reviews{rating}, so people clearly find you there."
            )
    else:
        parts.append(f"Здравейте, попаднах на {inp.name}, докато разглеждах {category} в {city}.")
        if inp.review_count and inp.review_count >= 50:
            parts.append(f"Имате {inp.review_count} отзива в Google, така че хората явно ви намират там.")

    observation, value = _observation_and_value(primary, inp, result, lang)
    if observation:
        parts.append(observation)
    if value:
        parts.append(value)
    parts.append(
        "Would you be open to a quick 10-minute chat this week?"
        if lang == "en"
        else "Имате ли 10 минути тази седмица за кратък разговор?"
    )

    talking_points = [r.text for r in result.reasons if r.opportunity is not None]
    if audit and audit.facts.get("booking_providers"):
        talking_points.append("Already uses: " + ", ".join(audit.facts["booking_providers"]))
    return Pitch(lang, " ".join(parts), primary.value if primary else None, talking_points)


def _observation_and_value(
    primary: OpportunityType | None, inp: ScoringInput, result: ScoreResult, lang: str
) -> tuple[str | None, str | None]:
    en = lang == "en"
    audit = inp.audit
    site_value = (
        "We build fast, mobile-friendly websites for local businesses so people who find you on Google can call "
        "or book directly."
        if en
        else "Правим бързи и удобни за телефон сайтове за местни бизнеси, така че хората, които ви намират в Google, "
        "да могат директно да се обадят или да запазят час."
    )
    modern_value = (
        "We modernise websites so they load fast and work well on phones."
        if en
        else "Модернизираме сайтове, така че да се зареждат бързо и да работят добре на телефон."
    )
    conversion_value = (
        "We help local businesses turn website visitors into calls and inquiries."
        if en
        else "Помагаме на местни бизнеси да превръщат посетителите на сайта си в обаждания и запитвания."
    )
    google_value = (
        "We help local businesses complete and strengthen their Google presence."
        if en
        else "Помагаме на местни бизнеси да изградят пълноценно присъствие в Google."
    )

    if primary == OpportunityType.NO_WEBSITE:
        kind = inp.website_kind
        if kind == "social":
            obs = (
                "I noticed your Google listing links to your social media page rather than a website of your own."
                if en
                else "Забелязах, че профилът ви в Google води към страница в социална мрежа, а не към собствен уебсайт."
            )
        elif kind == "booking_platform":
            name = (domain_of(inp.website_url) or "booking").split(".")[0].capitalize()
            obs = (
                f"I noticed your Google listing links to your {name} page rather than a website of your own."
                if en
                else f"Забелязах, че профилът ви в Google води към страницата ви в {name}, а не към собствен уебсайт."
            )
        else:
            obs = (
                "I noticed your Google listing doesn't include a website."
                if en
                else "Забелязах, че в профила ви в Google няма посочен уебсайт."
            )
        return obs, site_value
    if primary == OpportunityType.BROKEN_WEBSITE:
        codes = audit.signal_codes if audit else set()
        if "parked_domain" in codes:
            obs = (
                "Your website address currently shows a parked-domain page."
                if en
                else "Адресът на сайта ви в момента показва паркиран домейн."
            )
        elif "under_construction" in codes:
            obs = (
                "Your website currently shows an 'under construction' page."
                if en
                else "Сайтът ви в момента показва страница „в процес на разработка“."
            )
        else:
            reason = (audit.error_message or "").lower() if audit else ""
            obs = (
                f"When I tried to open your website, it didn't load{f' ({reason})' if reason else ''}."
                if en
                else "Опитах да отворя сайта ви, но той не се зареди."
            )
        return obs, site_value
    if primary == OpportunityType.NO_BOOKING:
        if not inp.website_url or inp.website_kind != "own":
            obs = (
                "I couldn't find a way to book with you online."
                if en
                else "Не открих начин за онлайн резервация при вас."
            )
        else:
            obs = (
                "I noticed your site doesn't currently show an online booking option."
                if en
                else "Забелязах, че на сайта ви в момента няма възможност за онлайн резервация."
            )
        return obs, (
            "We help businesses turn Google visitors into direct bookings."
            if en
            else "Помагаме на бизнесите да превръщат посетителите от Google в директни резервации."
        )
    if primary == OpportunityType.MOBILE_PROBLEM:
        return (
            "Your site doesn't appear to be set up for phone screens."
            if en
            else "Сайтът ви не изглежда пригоден за мобилни телефони."
        ), modern_value
    if primary in (OpportunityType.WEBSITE_REDESIGN, OpportunityType.OUTDATED_WEBSITE):
        issues = _top_issues(result, inp)
        if en and issues:
            return (
                f"I ran a quick check of your website and noticed a few things, for example: {_join(issues, 'and')}.",
                modern_value,
            )
        count = len([s for s in (audit.signals if audit else []) if (s.get("penalty") or 0) > 0])
        return (
            (
                "I ran a quick check of your website and noticed a few things that could be improved."
                if en
                else f"Направих бърза проверка на сайта ви и открих {count} неща, които могат да се подобрят."
            ),
            modern_value,
        )
    if primary == OpportunityType.NO_CONTACT_CTA:
        return (
            "I couldn't find a clear 'call' or 'book' button on your website."
            if en
            else "Не открих ясен бутон за обаждане или резервация на сайта ви."
        ), conversion_value
    if primary == OpportunityType.WEAK_CONVERSION:
        missing = result.missing_conversion[:3]
        if en:
            return (
                f"Your website doesn't show {_join(missing, 'or')}, which makes it harder for visitors to get "
                "in touch."
            ), conversion_value
        return (
            f"На сайта ви не открих {_join([MISSING_BG.get(m, m) for m in missing], 'и')}, които улесняват "
            "клиентите да се свържат с вас."
        ), conversion_value
    if primary == OpportunityType.SLOW_WEBSITE and audit and audit.response_time_ms:
        seconds = audit.response_time_ms / 1000
        return (
            (
                f"Your homepage took about {seconds:.0f} seconds to load in my test."
                if en
                else f"Началната ви страница се зареди за около {seconds:.0f} секунди при моя тест."
            ),
            modern_value,
        )
    if primary in (OpportunityType.MISSING_BUSINESS_INFO, OpportunityType.GOOGLE_PROFILE):
        items = [GOOGLE_MISSING[c][0 if en else 1] for c in GOOGLE_MISSING if c in result.google.codes]
        if items:
            return (
                (
                    f"Your Google profile is missing {_join(items, 'and')}."
                    if en
                    else f"В профила ви в Google липсват {_join(items, 'и')}."
                ),
                google_value,
            )
    if primary == OpportunityType.LOW_REVIEWS and inp.review_count is not None:
        return (
            (
                f"Your Google profile has {inp.review_count} reviews so far."
                if en
                else f"Профилът ви в Google има {inp.review_count} отзива засега."
            ),
            google_value,
        )
    return None, None
