"""Demo provider: deterministic, clearly synthetic businesses for UI testing
without spending API credits. Only active when DEMO_MODE=true.

* Every name starts with "Demo".
* Phone numbers come from Ofcom's ranges reserved for fiction
  (+44 20 7946 0xxx, +44 113 496 0xxx) so they can never reach a real person;
  dialing is additionally disabled in the UI for demo records.
* Websites live under the reserved ``.invalid`` TLD and are served by the
  demo site fixtures (see ``app.audit.demo_sites``).
* No Google Maps URL is fabricated.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.providers.base import BusinessSearchResult, ProviderNotFoundError, ProviderPlace, SearchParams

PROVIDER_NAME = "demo"
DEMO_TLD = "demo.invalid"

WEBSITE_VARIANTS = [
    "none", "modern", "outdated", "none", "nobooking", "social", "outdated", "none", "parked",
    "modern", "nobooking", "broken", "construction", "none", "outdated", "nobooking", "booking_platform",
    "modern", "none", "outdated",
]  # fmt: skip

_CATEGORY_WORDS: dict[str, tuple[str, str]] = {
    "gym": ("Gym", "gym"),
    "fitness": ("Fitness Club", "fitness_center"),
    "trainer": ("Personal Training", "gym"),
    "beauty": ("Beauty Studio", "beauty_salon"),
    "nail": ("Nail Bar", "nail_salon"),
    "hair": ("Hair Salon", "hair_salon"),
    "barber": ("Barber", "barber_shop"),
    "restaurant": ("Restaurant", "restaurant"),
    "cafe": ("Cafe", "cafe"),
    "coffee": ("Coffee House", "cafe"),
    "detailing": ("Car Detailing", "car_wash"),
    "dentist": ("Dental Clinic", "dentist"),
    "dental": ("Dental Clinic", "dentist"),
    "physio": ("Physio Center", "physiotherapist"),
    "real estate": ("Real Estate", "real_estate_agency"),
    "estate": ("Real Estate", "real_estate_agency"),
}

_TYPE_LABELS = {
    "gym": "Gym", "fitness_center": "Fitness center", "beauty_salon": "Beauty salon", "nail_salon": "Nail salon",
    "hair_salon": "Hair salon", "barber_shop": "Barber shop", "restaurant": "Restaurant", "cafe": "Cafe",
    "car_wash": "Car wash", "dentist": "Dentist", "physiotherapist": "Physiotherapist",
    "real_estate_agency": "Real estate agency", "establishment": "Business",
}  # fmt: skip

_STREETS = [
    "Demo Street",
    "Sample Boulevard",
    "Example Avenue",
    "Test Lane",
    "Placeholder Road",
    "Mock Square",
]


def _h(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16)


def _parse_query(text: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s+in\s+(.+)$", text.strip(), flags=re.I)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text.strip(), "Sofia"


def _category(category: str) -> tuple[str, str]:
    lowered = category.lower()
    for word, value in _CATEGORY_WORDS.items():
        if word in lowered:
            return value
    title = category.strip().rstrip("s").title() or "Business"
    return title, "establishment"


def _hours(variant: int) -> dict[str, Any] | None:
    if variant == 0:
        return None  # unknown hours
    close_hour = 21 if variant in (1, 2, 3) else 18
    open_days = range(1, 7) if variant != 3 else range(0, 7)
    periods = [
        {"open": {"day": d, "hour": 9, "minute": 0}, "close": {"day": d, "hour": close_hour, "minute": 0}}
        for d in open_days
    ]
    names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    descriptions = [
        f"{names[d]}: {'9:00 AM – ' + str(close_hour - 12) + ':00 PM' if d in open_days else 'Closed'}"
        for d in [1, 2, 3, 4, 5, 6, 0]
    ]
    return {"periods": periods, "weekday_descriptions": descriptions}


def build_demo_place(category: str, location: str, index: int) -> ProviderPlace:
    title, place_type = _category(category)
    seed = _h(category.lower(), location.lower(), str(index))
    city = location.split(",")[-1].strip() or "Sofia"
    neighborhood = location.split(",")[0].strip() if "," in location else None
    slug = re.sub(r"[^a-z0-9]+", "-", f"demo {title} {neighborhood or city} {index:02d}".lower()).strip("-")
    variant = WEBSITE_VARIANTS[seed % len(WEBSITE_VARIANTS)]

    website: str | None
    if variant == "none":
        website = None
    elif variant == "social":
        website = f"https://www.facebook.com/{slug}"
    elif variant == "booking_platform":
        website = f"https://booksy.com/en-us/{seed % 100000}_{slug}"
    else:
        website = f"https://{slug}.{variant}.{DEMO_TLD}/"

    has_phone = seed % 10 != 0
    if has_phone:
        suffix = f"{seed % 1000:03d}"
        international = f"+44 20 7946 0{suffix}" if seed % 2 else f"+44 113 496 0{suffix}"
    else:
        international = None

    review_count = [0, 3, 8, 14, 27, 45, 88, 132, 217, 390][(seed >> 4) % 10]
    rating = None if review_count == 0 else round(3.6 + ((seed >> 8) % 15) / 10, 1)
    photo_count = [0, 1, 2, 5, 10, 10][(seed >> 12) % 6]

    return ProviderPlace(
        provider=PROVIDER_NAME,
        external_id=f"demo-{seed:012x}",
        name=f"Demo {title} {neighborhood or city} {index:02d}",
        primary_type=place_type,
        primary_type_label=_TYPE_LABELS.get(place_type, title),
        types=[place_type, "point_of_interest", "establishment"],
        formatted_address=f"{(seed % 180) + 1} {_STREETS[seed % len(_STREETS)]}, {neighborhood + ', ' if neighborhood else ''}{city}",
        city=city,
        neighborhood=neighborhood,
        postal_code=None,
        country_code="BG",
        latitude=None,
        longitude=None,
        national_phone=None,
        international_phone=international,
        website_url=website,
        maps_url=None,
        rating=min(rating, 5.0) if rating else None,
        review_count=review_count,
        opening_hours=_hours((seed >> 16) % 6),
        utc_offset_minutes=180,
        business_status="OPERATIONAL" if seed % 23 else "CLOSED_TEMPORARILY",
        photo_count=photo_count,
        description=None,
        description_requested=False,
        raw={"demo": True, "variant": variant},
        is_demo=True,
    )


class DemoProvider:
    name = PROVIDER_NAME
    search_sku = "demo"
    details_sku = "demo"

    def is_configured(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def search_businesses(self, params: SearchParams) -> BusinessSearchResult:
        category, location = _parse_query(params.text_query)
        total = 25 + _h(category.lower(), location.lower()) % 21  # 25..45 results per query
        offset = int(params.page_token.split(":")[1]) if params.page_token else 0
        size = max(1, min(params.page_size, 20))
        places = [
            build_demo_place(category, location, i + 1) for i in range(offset, min(offset + size, total))
        ]
        if params.min_rating:
            places = [p for p in places if p.rating is not None and p.rating >= params.min_rating]
        next_offset = offset + size
        return BusinessSearchResult(
            places=places,
            next_page_token=f"demo:{next_offset}" if next_offset < total else None,
            sku=self.search_sku,
        )

    async def get_business_details(
        self, external_id: str, *, language_code: str | None = None, region_code: str | None = None
    ) -> ProviderPlace:
        raise ProviderNotFoundError("Demo businesses cannot be refreshed from a provider.")
