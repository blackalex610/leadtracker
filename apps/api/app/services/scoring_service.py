"""Bridges the database models and the pure scoring engine."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.enums import PRIORITY_RANK
from app.core.opening_hours import open_in_window_on_weekdays
from app.log import get_logger
from app.models import Business, WebsiteAudit
from app.scoring.data_quality import data_quality
from app.scoring.engine import ScoreResult, calculate_opportunity_score, is_booking_oriented
from app.scoring.inputs import AuditSnapshot, NicheInfo, ScoringInput
from app.scoring.pitch import Pitch, build_pitch
from app.services.presets import resolve_niche
from app.services.settings import RuntimeSettings

log = get_logger(__name__)


def audit_snapshot(audit: WebsiteAudit | None) -> AuditSnapshot | None:
    if audit is None:
        return None
    return AuditSnapshot(
        status=audit.status,
        error_code=audit.error_code,
        error_message=audit.error_message,
        health_score=audit.health_score,
        outdated_score=audit.outdated_score,
        outdated_band=audit.outdated_band,
        response_time_ms=audit.response_time_ms,
        signals=list(audit.signals or []),
        facts=dict(audit.facts or {}),
    )


def scoring_input(
    business: Business, audit: WebsiteAudit | None, niche: NicheInfo | None, runtime: RuntimeSettings
) -> ScoringInput:
    periods = (business.opening_hours or {}).get("periods") if business.opening_hours else None
    open_window = open_in_window_on_weekdays(
        periods, runtime.calling.window_start, runtime.calling.window_end
    )
    return ScoringInput(
        name=business.name,
        category=business.category,
        primary_type=business.primary_type,
        types=list(business.types or []),
        city=business.city or runtime.general.default_city,
        niche=niche,
        has_phone=bool(business.normalized_phone),
        phone_invalid=business.phone_invalid,
        website_url=business.website_url,
        website_kind=business.website_kind,
        website_status=business.website_status,
        audit=audit_snapshot(audit) if business.website_status != "unaudited" else None,
        rating=business.rating,
        review_count=business.review_count,
        opening_hours=business.opening_hours,
        address=business.address,
        business_status=business.business_status,
        photo_count=business.photo_count,
        description=business.description,
        description_requested=get_settings().places_field_tier == "enterprise_atmosphere"
        and business.provider == "google_places",
        open_in_calling_window=open_window,
        provider=business.provider,
    )


async def load_last_audit(session: AsyncSession, business: Business) -> WebsiteAudit | None:
    if business.last_audit_id is None:
        return None
    return await session.get(WebsiteAudit, business.last_audit_id)


async def rescore_business(
    session: AsyncSession,
    business: Business,
    runtime: RuntimeSettings,
    niches: list[NicheInfo],
    audit: WebsiteAudit | None = None,
) -> ScoreResult:
    if audit is None:
        audit = await load_last_audit(session, business)
    niche = resolve_niche(business, niches)
    inp = scoring_input(business, audit, niche, runtime)
    result = calculate_opportunity_score(inp, runtime.scoring)

    business.opportunity_score = result.score
    business.priority = result.priority.value
    business.priority_rank = PRIORITY_RANK[result.priority]
    business.priority_reason = result.priority_reason
    business.opportunity_types = [o.value for o in result.opportunities]
    business.score_reasons = [r.to_dict() for r in result.reasons] + [
        {"rule": None, "points": 0, "text": note, "opportunity": None, "tier": "note"}
        for note in result.notes
    ]
    business.strong_category = result.strong_category
    business.booking_oriented = result.booking_oriented
    business.google_profile_score = result.google.score
    business.google_signals = result.google.signals
    business.open_in_calling_window = inp.open_in_calling_window
    grade, _ = data_quality(
        has_phone=bool(business.normalized_phone),
        website_url=business.website_url,
        address=business.address,
        rating=business.rating,
        opening_hours=business.opening_hours,
    )
    business.data_quality = grade.value
    business.scored_at = datetime.now(UTC)
    log.info(
        "lead_scored",
        business_id=business.id,
        score=result.score,
        priority=result.priority.value,
        opportunities=business.opportunity_types,
    )
    return result


def pitch_for(
    business: Business,
    audit: WebsiteAudit | None,
    niches: list[NicheInfo],
    runtime: RuntimeSettings,
    language: str,
) -> tuple[Pitch, ScoreResult]:
    niche = resolve_niche(business, niches)
    inp = scoring_input(business, audit, niche, runtime)
    result = calculate_opportunity_score(inp, runtime.scoring)
    return build_pitch(inp, result, language), result


def booking_expected(business: Business, niches: list[NicheInfo], runtime: RuntimeSettings) -> bool:
    niche = resolve_niche(business, niches)
    inp = ScoringInput(
        name=business.name, primary_type=business.primary_type, types=list(business.types or []), niche=niche
    )
    return is_booking_oriented(inp, runtime.scoring)
