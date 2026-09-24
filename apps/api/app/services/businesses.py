"""Creating and updating businesses from provider places and imported rows,
with de-duplication, phone normalization and suppression enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LeadStatus, PhoneSource, WebsiteStatus
from app.core.phone import normalize_phone
from app.core.text import address_key, dedupe_domain, domain_of, name_key, normalize_url, website_kind
from app.log import get_logger
from app.models import Business, BusinessContact, BusinessSource, LeadEvent
from app.providers.base import ProviderPlace
from app.services.dedupe import DedupeCandidate, find_match
from app.services.suppression import is_suppressed

log = get_logger(__name__)

# Fields a provider refresh may overwrite on an existing record it owns.
PROVIDER_OWNED = (
    "name", "category", "primary_type", "types", "address", "city", "neighborhood", "postal_code",
    "country_code", "latitude", "longitude", "google_maps_url", "rating", "review_count", "opening_hours",
    "utc_offset_minutes", "business_status", "photo_count", "description",
)  # fmt: skip


@dataclass(slots=True)
class BusinessRecord:
    name: str
    provider: str
    external_id: str | None = None
    category: str | None = None
    primary_type: str | None = None
    types: list[str] = field(default_factory=list)
    address: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phones: list[str] = field(default_factory=list)
    phone_source: str = PhoneSource.GOOGLE_PLACES.value
    website_url: str | None = None
    google_maps_url: str | None = None
    rating: float | None = None
    review_count: int | None = None
    opening_hours: dict[str, Any] | None = None
    utc_offset_minutes: int | None = None
    business_status: str | None = None
    photo_count: int | None = None
    description: str | None = None
    raw: dict[str, Any] | None = None
    fetched_at: datetime | None = None
    is_demo: bool = False


def record_from_place(place: ProviderPlace) -> BusinessRecord:
    return BusinessRecord(
        name=place.name,
        provider=place.provider,
        external_id=place.external_id,
        category=place.primary_type_label,
        primary_type=place.primary_type,
        types=place.types,
        address=place.formatted_address,
        city=place.city,
        neighborhood=place.neighborhood,
        postal_code=place.postal_code,
        country_code=place.country_code,
        latitude=place.latitude,
        longitude=place.longitude,
        phones=[p for p in (place.international_phone, place.national_phone) if p],
        phone_source=PhoneSource.DEMO.value if place.is_demo else PhoneSource.GOOGLE_PLACES.value,
        website_url=place.website_url,
        google_maps_url=place.maps_url,
        rating=place.rating,
        review_count=place.review_count,
        opening_hours=place.opening_hours,
        utc_offset_minutes=place.utc_offset_minutes,
        business_status=place.business_status,
        photo_count=place.photo_count,
        description=place.description,
        raw=place.raw,
        fetched_at=place.fetched_at,
        is_demo=place.is_demo,
    )


@dataclass(slots=True)
class UpsertOutcome:
    business: Business
    created: bool
    match_reason: str | None
    website_changed: bool = False


def _normalized_phones(record: BusinessRecord, region: str) -> list[tuple[str, Any]]:
    seen: dict[str, Any] = {}
    for raw in record.phones:
        normalized = normalize_phone(raw, record.country_code or region)
        if normalized and normalized.e164 not in seen:
            seen[normalized.e164] = normalized
    return list(seen.items())


def set_website(business: Business, url: str | None) -> bool:
    normalized = normalize_url(url)
    if normalized == business.website_url:
        return False
    business.website_url = normalized
    business.website_domain = dedupe_domain(normalized) or domain_of(normalized)
    business.website_kind = website_kind(normalized)
    if not normalized:
        business.website_status = WebsiteStatus.NONE.value
    elif business.website_kind == "own":
        business.website_status = WebsiteStatus.UNAUDITED.value
    else:
        business.website_status = WebsiteStatus.NONE.value
    business.website_health_score = None
    business.outdated_score = None
    return True


async def _ensure_contacts(
    session: AsyncSession, business: Business, phones: list[tuple[str, Any]], source: str, make_primary: bool
) -> None:
    if not phones:
        return
    existing = {
        c.normalized_phone: c
        for c in (
            await session.execute(select(BusinessContact).where(BusinessContact.business_id == business.id))
        ).scalars()
    }
    for index, (e164, normalized) in enumerate(phones):
        if e164 not in existing:
            session.add(
                BusinessContact(
                    business_id=business.id,
                    raw_phone=normalized.raw,
                    normalized_phone=e164,
                    national_format=normalized.national,
                    international_format=normalized.international,
                    country_code=normalized.country_code,
                    phone_type=normalized.phone_type,
                    phone_source=source,
                    is_primary=False,
                )
            )
        if index == 0 and (make_primary or not business.normalized_phone):
            if business.normalized_phone != e164:
                business.phone_verified = False
                business.phone_invalid = False
            business.phone_raw = normalized.raw
            business.normalized_phone = e164
            business.national_phone = normalized.national
            business.international_phone = normalized.international
            business.phone_country_code = normalized.country_code
            business.phone_type = normalized.phone_type
            business.phone_source = source
    await session.flush()
    for contact in (
        await session.execute(select(BusinessContact).where(BusinessContact.business_id == business.id))
    ).scalars():
        contact.is_primary = contact.normalized_phone == business.normalized_phone


async def _apply_suppression(session: AsyncSession, business: Business) -> None:
    if business.normalized_phone and await is_suppressed(session, business.normalized_phone):
        business.suppressed = True
        business.status = LeadStatus.DO_NOT_CONTACT.value


def _fill_empty(business: Business, record: BusinessRecord) -> None:
    """Fill only fields that are currently empty — never overwrite existing data."""
    for attr in PROVIDER_OWNED:
        value = getattr(record, attr)
        if value in (None, [], "") or getattr(business, attr) not in (None, [], ""):
            continue
        setattr(business, attr, value)
        if attr == "address":
            business.address_key = address_key(record.address, record.city)


def _overwrite_provider_fields(business: Business, record: BusinessRecord) -> None:
    for attr in PROVIDER_OWNED:
        value = getattr(record, attr)
        if attr in ("latitude", "longitude") and value is None:
            continue
        setattr(business, attr, value)
    if record.latitude is not None:
        business.latlng_fetched_at = record.fetched_at or datetime.now(UTC)


async def upsert_business(
    session: AsyncSession,
    record: BusinessRecord,
    *,
    default_region: str = "BG",
    niche_key: str | None = None,
    user_id: int | None = None,
    fill_only: bool = False,
) -> UpsertOutcome:
    """Insert or update one business. ``fill_only`` never overwrites existing
    values (used for CSV imports)."""
    phones = _normalized_phones(record, default_region)
    cand = DedupeCandidate(
        name_key=name_key(record.name),
        provider=record.provider if record.external_id else None,
        external_id=record.external_id,
        normalized_phone=phones[0][0] if phones else None,
        website_domain=dedupe_domain(record.website_url),
        address_key=address_key(record.address, record.city),
    )
    match = await find_match(session, cand)
    now = datetime.now(UTC)

    if match is not None:
        business = match.business
        same_source = match.reason == "provider_place_id"
        website_changed = False
        if same_source and not fill_only:
            _overwrite_provider_fields(business, record)
            business.name_key = cand.name_key
            business.address_key = cand.address_key
            website_changed = set_website(business, record.website_url)
            business.source_timestamp = record.fetched_at or now
        else:
            _fill_empty(business, record)
            if not business.website_url and record.website_url:
                website_changed = set_website(business, record.website_url)
        if not business.niche_key and niche_key:
            business.niche_key = niche_key
        await _ensure_contacts(
            session, business, phones, record.phone_source, make_primary=same_source and not fill_only
        )
        if record.external_id:
            await _link_source(session, business, record, match.reason, now)
        await _apply_suppression(session, business)
        log.info("business_duplicate", business_id=business.id, reason=match.reason)
        return UpsertOutcome(
            business, created=False, match_reason=match.reason, website_changed=website_changed
        )

    business = Business(
        name=record.name[:300],
        name_key=cand.name_key[:300],
        address_key=cand.address_key,
        provider=record.provider,
        provider_place_id=record.external_id,
        source_timestamp=record.fetched_at or now,
        niche_key=niche_key,
        created_by_id=user_id,
        is_demo=record.is_demo,
        types=[],
        opportunity_types=[],
        score_reasons=[],
        google_signals=[],
    )
    _overwrite_provider_fields(business, record)
    business.types = record.types or []
    set_website(business, record.website_url)
    if not business.website_url:
        business.website_status = WebsiteStatus.NONE.value

    try:
        async with session.begin_nested():
            session.add(business)
            await session.flush()
            if record.external_id:
                await _link_source(session, business, record, None, now)
    except IntegrityError:
        # Another worker inserted the same place concurrently: retry as an update.
        log.info("business_insert_race", external_id=record.external_id)
        return await upsert_business(
            session,
            record,
            default_region=default_region,
            niche_key=niche_key,
            user_id=user_id,
            fill_only=fill_only,
        )
    await _ensure_contacts(session, business, phones, record.phone_source, make_primary=True)
    if not phones and record.phones:
        business.phone_raw = record.phones[0][:64]
    await _apply_suppression(session, business)
    session.add(
        LeadEvent(
            business_id=business.id, user_id=user_id, type="created", data={"provider": record.provider}
        )
    )
    log.info("business_discovered", business_id=business.id, provider=record.provider)
    return UpsertOutcome(
        business, created=True, match_reason=None, website_changed=bool(business.website_url)
    )


async def _link_source(
    session: AsyncSession, business: Business, record: BusinessRecord, reason: str | None, now: datetime
) -> None:
    source = (
        await session.execute(
            select(BusinessSource).where(
                BusinessSource.provider == record.provider, BusinessSource.external_id == record.external_id
            )
        )
    ).scalar_one_or_none()
    if source is None:
        session.add(
            BusinessSource(
                business_id=business.id,
                provider=record.provider,
                external_id=record.external_id or "",
                match_reason=reason,
                raw=record.raw,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        await session.flush()
    else:
        source.last_seen_at = now
        source.raw = record.raw
