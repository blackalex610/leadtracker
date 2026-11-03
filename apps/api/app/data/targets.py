"""Built-in ICP search targets: the business types "Find leads" searches on its own.

There is nothing to pick: one click works through this list, best-paying and
most-likely-to-lack-a-website first, and skips any query already run recently,
so every search brings fresh businesses.

Why these businesses (ideal customer profile for a website / local-promotion
offer sold by phone in Bulgaria):

* Customers find them by searching Google on a phone ("ключар София",
  "автосервиз Люлин"), so a missing or broken website loses them jobs every day.
* Owner-operated: the number on the listing is usually the owner's mobile, so
  the decision maker answers the cold call.
* A single customer is worth far more than the offer price (a renovation, a
  dental implant, a wedding hall booking), so a €290 site pays for itself fast.
* Trades and home services have the highest no-website share of any group
  (roughly 4 in 10 listings), and Bulgaria has the EU's lowest business use of
  social media and digital tools - the gap is big and the pitch is easy.

``value_tier`` (1-3) is how much a typical customer is worth to the business:
tier 3 businesses can pay the premium price. ``booking`` marks businesses whose
customers book an appointment or a slot (online booking is a sellable extra).
Query texts are Bulgarian because Google ranks local results best that way.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Target:
    key: str
    label: str
    label_bg: str
    query: str
    group: str
    value_tier: int = 2
    booking: bool = False
    included_type: str | None = None
    match_types: tuple[str, ...] = field(default_factory=tuple)


# Order matters: the planner runs earlier targets first.
TARGETS: tuple[Target, ...] = (
    # --- home services & trades: urgent search, high-value jobs, often no website ---------
    Target("plumbers", "Plumbers", "ВиК услуги", "ВиК услуги", "home", 3, match_types=("plumber",)),
    Target("electricians", "Electricians", "електротехници", "електротехник", "home", 3,
           match_types=("electrician",)),
    Target("renovations", "Renovation contractors", "фирми за ремонти", "ремонт на апартаменти", "home", 3,
           match_types=("general_contractor",)),
    Target("windows_doors", "Windows & doors", "фирми за дограма", "PVC дограма", "home", 3),
    Target("hvac", "AC & heating service", "сервизи за климатици", "ремонт на климатици", "home", 3),
    Target("roofing", "Roofers", "фирми за покриви", "ремонт на покриви", "home", 3,
           match_types=("roofing_contractor",)),
    Target("furniture", "Custom furniture", "мебели по поръчка", "мебели по поръчка", "home", 3,
           match_types=("furniture_store",)),
    Target("locksmiths", "Locksmiths", "ключари", "ключар", "home", 2, match_types=("locksmith",)),
    Target("appliance_repair", "Appliance repair", "сервизи за ремонт на уреди", "ремонт на перални", "home", 2),
    Target("movers", "Movers", "хамалски услуги", "хамалски услуги", "home", 2, match_types=("moving_company",)),
    Target("cleaning", "Cleaning services", "фирми за почистване", "почистване на домове", "home", 2),
    Target("pest_control", "Pest control", "фирми за дезинсекция", "дезинсекция", "home", 2),
    # --- auto -------------------------------------------------------------------------------
    Target("car_repair", "Car repair", "автосервизи", "автосервиз", "auto", 2, booking=True,
           match_types=("car_repair",)),
    Target("driving_schools", "Driving schools", "автошколи", "автошкола", "auto", 3,
           match_types=("driving_school",)),
    Target("tyres", "Tyre shops", "вулканизатори", "вулканизатор", "auto", 2, booking=True,
           match_types=("car_repair",)),
    Target("car_detailing", "Car detailing", "автодетайлинг", "автодетайлинг", "auto", 2, booking=True,
           match_types=("car_wash",)),
    Target("towing", "Towing & roadside help", "пътна помощ", "пътна помощ", "auto", 2),
    # --- health: high-value patients, appointment based -----------------------------------
    Target("dentists", "Dental clinics", "дентални кабинети", "дентален кабинет", "health", 3, booking=True,
           included_type="dentist", match_types=("dentist", "dental_clinic")),
    Target("physio", "Physiotherapy", "физиотерапевтични центрове", "физиотерапия", "health", 2, booking=True,
           included_type="physiotherapist", match_types=("physiotherapist", "chiropractor")),
    Target("vets", "Vet clinics", "ветеринарни клиники", "ветеринарна клиника", "health", 2, booking=True,
           match_types=("veterinary_care",)),
    # --- events & creative: one booking pays for the site ----------------------------------
    Target("event_venues", "Event halls", "зали за събития", "зала за събития", "events", 3, booking=True,
           match_types=("event_venue", "wedding_venue", "banquet_hall")),
    Target("photographers", "Photographers", "фотографи", "фотограф", "events", 2,
           match_types=("photographer",)),
    Target("kids_parties", "Kids party venues", "детски центрове", "детски център за рождени дни", "events", 2,
           booking=True),
    Target("cakes", "Custom cakes", "торти по поръчка", "торти по поръчка", "events", 1,
           match_types=("bakery", "confectionery")),
    # --- beauty & wellness: book by phone/Instagram, love a booking page ----------------------
    Target("beauty_salons", "Beauty & cosmetics salons", "козметични салони", "козметичен салон", "beauty", 2,
           booking=True, included_type="beauty_salon",
           match_types=("beauty_salon", "skin_care_clinic", "beautician", "spa")),
    Target("tattoo", "Tattoo studios", "тату студиа", "тату студио", "beauty", 2, booking=True),
    Target("hair_salons", "Hair salons", "фризьорски салони", "фризьорски салон", "beauty", 1, booking=True,
           included_type="hair_salon", match_types=("hair_salon", "hair_care")),
    Target("barbers", "Barbers", "бръснарници", "бръснарница", "beauty", 1, booking=True,
           included_type="barber_shop", match_types=("barber_shop",)),
    Target("nail_salons", "Nail salons", "маникюрни салони", "маникюр", "beauty", 1, booking=True,
           included_type="nail_salon", match_types=("nail_salon",)),
    Target("massage", "Massage studios", "масажни студиа", "масажно студио", "beauty", 1, booking=True,
           match_types=("massage", "spa")),
    # --- other local services ------------------------------------------------------------------
    Target("gyms", "Gyms & fitness studios", "фитнес зали", "фитнес", "fitness", 2, booking=True,
           included_type="gym", match_types=("gym", "fitness_center", "yoga_studio")),
    Target("tutoring", "Tutoring & language schools", "учебни центрове", "езикова школа", "education", 2),
    Target("accountants", "Accountants", "счетоводни кантори", "счетоводна кантора", "business", 2,
           match_types=("accounting",)),
    Target("guest_houses", "Guest houses & small hotels", "къщи за гости", "къща за гости", "stay", 3,
           booking=True, match_types=("guest_house", "lodging", "hotel", "bed_and_breakfast")),
)  # fmt: skip

TARGETS_BY_KEY: dict[str, Target] = {t.key: t for t in TARGETS}

GROUP_LABELS: dict[str, str] = {
    "home": "Home services & trades",
    "auto": "Auto",
    "health": "Health",
    "events": "Events",
    "beauty": "Beauty & wellness",
    "fitness": "Fitness",
    "education": "Education",
    "business": "Business services",
    "stay": "Accommodation",
}


def target_for(target_key: str | None, primary_type: str | None, types: list[str] | None) -> Target | None:
    """The target a business was found with, else the first whose Google types match."""
    if target_key and target_key in TARGETS_BY_KEY:
        return TARGETS_BY_KEY[target_key]
    if primary_type:
        for target in TARGETS:
            if primary_type in target.match_types:
                return target
    if types:
        for target in TARGETS:
            if set(types) & set(target.match_types):
                return target
    return None
