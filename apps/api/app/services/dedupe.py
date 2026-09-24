"""Duplicate detection.

A candidate business is matched against existing records in this order:

1. ``provider + provider_place_id`` (exact, definitive);
2. normalized phone AND (similar name OR same website domain) — one lead per
   callable number, which also folds duplicate listings/branches that share a
   number;
3. own-website domain AND very similar name AND compatible address;
4. normalized name + normalized address (exact keys).

Shared platforms (facebook.com, booksy.com, ...) are never used as a domain signal.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Business, BusinessContact, BusinessSource

NAME_MATCH_WITH_PHONE = 85
NAME_MATCH_WITH_DOMAIN = 90
ADDRESS_MATCH = 90


@dataclass(slots=True)
class DedupeCandidate:
    name_key: str
    provider: str | None = None
    external_id: str | None = None
    normalized_phone: str | None = None
    website_domain: str | None = None
    address_key: str | None = None


@dataclass(slots=True)
class DedupeMatch:
    business: Business
    reason: str


def name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return float(fuzz.token_set_ratio(a, b))


def _address_compatible(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    return fuzz.token_set_ratio(a, b) >= ADDRESS_MATCH


async def find_match(session: AsyncSession, cand: DedupeCandidate) -> DedupeMatch | None:
    if cand.provider and cand.external_id:
        source = (
            await session.execute(
                select(BusinessSource).where(
                    BusinessSource.provider == cand.provider, BusinessSource.external_id == cand.external_id
                )
            )
        ).scalar_one_or_none()
        if source is not None:
            business = await session.get(Business, source.business_id)
            if business is not None:
                return DedupeMatch(business, "provider_place_id")

    if cand.normalized_phone:
        contact_ids = select(BusinessContact.business_id).where(
            BusinessContact.normalized_phone == cand.normalized_phone
        )
        rows = (
            (
                await session.execute(
                    select(Business)
                    .where(
                        or_(Business.normalized_phone == cand.normalized_phone, Business.id.in_(contact_ids))
                    )
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        for business in rows:
            if name_similarity(cand.name_key, business.name_key) >= NAME_MATCH_WITH_PHONE or (
                cand.website_domain and cand.website_domain == business.website_domain
            ):
                return DedupeMatch(business, "phone")

    if cand.website_domain:
        rows = (
            (
                await session.execute(
                    select(Business).where(Business.website_domain == cand.website_domain).limit(20)
                )
            )
            .scalars()
            .all()
        )
        for business in rows:
            if name_similarity(
                cand.name_key, business.name_key
            ) >= NAME_MATCH_WITH_DOMAIN and _address_compatible(cand.address_key, business.address_key):
                return DedupeMatch(business, "website_domain")

    if cand.name_key and cand.address_key:
        business = (
            await session.execute(
                select(Business)
                .where(Business.name_key == cand.name_key, Business.address_key == cand.address_key)
                .limit(1)
            )
        ).scalar_one_or_none()
        if business is not None:
            return DedupeMatch(business, "name_address")
    return None
