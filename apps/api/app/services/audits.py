"""Running and persisting website audits for businesses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditResult, WebsiteAuditor
from app.core.enums import LeadStatus, PhoneSource, WebsiteStatus
from app.core.phone import normalize_phone
from app.models import Business, BusinessContact, LeadEvent, WebsiteAudit
from app.services.suppression import is_suppressed


def needs_audit(business: Business, cache_days: int, force: bool = False) -> bool:
    if not business.website_url or business.website_kind != "own":
        return False
    if force or business.website_status == WebsiteStatus.UNAUDITED.value or business.last_audited_at is None:
        return True
    return business.last_audited_at < datetime.now(UTC) - timedelta(days=cache_days)


async def run_audit(
    auditor: WebsiteAuditor, url: str, *, booking_expected: bool, country_code: str
) -> AuditResult:
    return await auditor.audit(url, booking_expected=booking_expected, country_code=country_code)


async def persist_audit(
    session: AsyncSession, business: Business, result: AuditResult, job_id: int | None = None
) -> WebsiteAudit:
    audit = WebsiteAudit(
        business_id=business.id,
        job_id=job_id,
        url=result.url[:1000],
        final_url=(result.final_url or "")[:1000] or None,
        status=result.status.value,
        error_code=result.error_code,
        error_message=result.error_message,
        http_status=result.http_status,
        https=result.https,
        redirect_count=len(result.redirect_chain),
        redirect_chain=result.redirect_chain,
        response_time_ms=result.response_time_ms,
        health_score=result.health_score,
        outdated_score=result.outdated_score,
        outdated_band=result.outdated_band,
        category_scores=result.category_scores,
        signals=result.signals,
        outdated_signals=result.outdated_signals,
        facts=result.facts,
        pages=result.pages,
        analyzer_version=result.analyzer_version,
        started_at=result.started_at,
        finished_at=result.finished_at,
    )
    session.add(audit)
    await session.flush()

    business.last_audit_id = audit.id
    business.last_audited_at = audit.finished_at or datetime.now(UTC)
    business.website_status = result.website_status.value
    business.website_health_score = result.health_score
    business.outdated_score = result.outdated_score

    # A business without a phone on its listing may publish one on its website.
    if not business.normalized_phone:
        for raw in (result.facts or {}).get("phones_on_site_e164", [])[:1]:
            normalized = normalize_phone(raw, business.country_code or "BG")
            if normalized is None:
                continue
            exists = (
                await session.execute(
                    select(BusinessContact.id).where(
                        BusinessContact.business_id == business.id,
                        BusinessContact.normalized_phone == normalized.e164,
                    )
                )
            ).first()
            if not exists:
                session.add(
                    BusinessContact(
                        business_id=business.id,
                        raw_phone=normalized.raw,
                        normalized_phone=normalized.e164,
                        national_format=normalized.national,
                        international_format=normalized.international,
                        country_code=normalized.country_code,
                        phone_type=normalized.phone_type,
                        phone_source=PhoneSource.WEBSITE.value,
                        is_primary=True,
                    )
                )
            business.phone_raw = normalized.raw
            business.normalized_phone = normalized.e164
            business.national_phone = normalized.national
            business.international_phone = normalized.international
            business.phone_country_code = normalized.country_code
            business.phone_type = normalized.phone_type
            business.phone_source = PhoneSource.WEBSITE.value
            if await is_suppressed(session, normalized.e164):
                business.suppressed = True
                business.status = LeadStatus.DO_NOT_CONTACT.value

    session.add(
        LeadEvent(
            business_id=business.id,
            type="website_audit",
            data={
                "status": result.status.value,
                "health": result.health_score,
                "outdated": result.outdated_score,
                "error": result.error_code,
            },
        )
    )
    return audit
