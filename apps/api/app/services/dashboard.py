"""Dashboard aggregations. Every number answers a sales question."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    GOOGLE_OPPORTUNITIES,
    OPPORTUNITY_LABELS,
    WEBSITE_PROBLEM_OPPORTUNITIES,
    LeadCategory,
    LeadStatus,
    OpportunityType,
    Priority,
)
from app.models import Business, CallAttempt, Job, LeadEvent, WebsiteAudit
from app.scoring.category import CATEGORY_INFO, CATEGORY_ORDER, SELLABLE
from app.services.calling import callable_conditions
from app.services.leads import WEBSITE_PROBLEM_HEALTH, to_summary
from app.services.settings import RuntimeSettings
from app.services.usage import month_start, monthly_usage


async def dashboard(
    session: AsyncSession, runtime: RuntimeSettings, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    tz = ZoneInfo(runtime.general.timezone)
    local = now.astimezone(tz)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    day_end = day_start + timedelta(days=1)
    since_30 = now - timedelta(days=30)

    website_problem = or_(
        Business.website_status == "broken",
        Business.website_health_score < WEBSITE_PROBLEM_HEALTH,
        Business.opportunity_types.overlap([o.value for o in WEBSITE_PROBLEM_OPPORTUNITIES]),
    )
    kpis = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(Business.priority == Priority.HOT.value),
                func.count().filter(Business.priority == Priority.WARM.value),
                func.count().filter(Business.opportunity_types.overlap([OpportunityType.NO_WEBSITE.value])),
                func.count().filter(website_problem),
                func.count().filter(
                    Business.opportunity_types.overlap([o.value for o in GOOGLE_OPPORTUNITIES])
                ),
                func.count().filter(Business.normalized_phone.is_not(None)),
                func.count().filter(Business.call_count > 0),
                func.count().filter(
                    Business.status.in_(
                        [LeadStatus.INTERESTED.value, LeadStatus.QUALIFIED.value, LeadStatus.PROPOSAL.value]
                    )
                ),
                func.count().filter(
                    and_(
                        Business.next_callback_at.is_not(None),
                        Business.next_callback_at < day_end,
                        Business.suppressed.is_(False),
                    )
                ),
                func.count().filter(Business.suppressed.is_(True)),
                func.count().filter(Business.is_demo.is_(True)),
            )
        )
    ).one()
    calls_today = (
        await session.execute(
            select(func.count()).where(CallAttempt.created_at >= day_start, CallAttempt.created_at < day_end)
        )
    ).scalar_one()

    since_7 = now - timedelta(days=7)
    in_play = [LeadStatus.INTERESTED.value, LeadStatus.QUALIFIED.value, LeadStatus.PROPOSAL.value]
    won_recently = exists().where(
        LeadEvent.business_id == Business.id,
        LeadEvent.type == "updated",
        LeadEvent.created_at >= since_7,
        LeadEvent.data["status"]["to"].astext == LeadStatus.WON.value,
    )
    won = (
        await session.execute(
            select(func.coalesce(func.sum(Business.deal_value), 0), func.count()).where(
                Business.status == LeadStatus.WON.value, won_recently
            )
        )
    ).one()
    playing = (
        await session.execute(
            select(func.coalesce(func.sum(Business.deal_value), 0), func.count()).where(
                Business.status.in_(in_play)
            )
        )
    ).one()
    calls_7d = (
        await session.execute(select(func.count()).where(CallAttempt.created_at >= since_7))
    ).scalar_one()
    sellable = [c.value for c in SELLABLE]
    category_rows = (
        await session.execute(
            select(
                Business.lead_category,
                func.count(),
                func.coalesce(func.sum(Business.deal_value), 0),
                func.coalesce(func.sum(Business.expected_value), 0),
            )
            .where(*callable_conditions(), Business.status == LeadStatus.NEW.value)
            .group_by(Business.lead_category)
        )
    ).all()
    by_cat = {str(k): (int(n), int(d), int(e)) for k, n, d, e in category_rows if k}
    by_category = [
        {
            "key": c.value,
            "label": CATEGORY_INFO[c].label,
            "count": by_cat[c.value][0],
            "deal_value": by_cat[c.value][1],
            "expected_value": by_cat[c.value][2],
        }
        for c in CATEGORY_ORDER
        if c.value in by_cat and c != LeadCategory.NOT_A_FIT
    ]
    ready = [by_cat[c] for c in sellable if c in by_cat]

    opp_rows = (
        await session.execute(
            select(func.unnest(Business.opportunity_types).label("opp"), func.count()).group_by("opp")
        )
    ).all()
    opp_counts = [(OpportunityType(k), int(c)) for k, c in opp_rows if k in OpportunityType.__members__]
    by_opportunity = [
        {"key": opp.value, "label": OPPORTUNITY_LABELS.get(opp, opp.value), "count": count}
        for opp, count in sorted(opp_counts, key=lambda item: -item[1])
    ]
    outcome_rows = (
        await session.execute(
            select(CallAttempt.outcome, func.count())
            .where(CallAttempt.created_at >= since_30)
            .group_by(CallAttempt.outcome)
        )
    ).all()
    status_rows = (
        await session.execute(select(Business.status, func.count()).group_by(Business.status))
    ).all()
    status_counts = {str(k): int(v) for k, v in status_rows}
    pipeline = [{"key": s.value, "count": status_counts.get(s.value, 0)} for s in LeadStatus]
    priority_rows = (
        await session.execute(select(Business.priority, func.count()).group_by(Business.priority))
    ).all()

    # Month-to-date usage
    start = month_start(now)
    month = (
        await session.execute(
            select(
                func.count().filter(Business.created_at >= start),
                func.count().filter(
                    and_(Business.created_at >= start, Business.normalized_phone.is_not(None))
                ),
            )
        )
    ).one()
    audits_month = (
        await session.execute(
            select(func.count()).select_from(WebsiteAudit).where(WebsiteAudit.started_at >= start)
        )
    ).scalar_one()
    searches_month = (
        await session.execute(
            select(func.count()).select_from(Job).where(Job.kind == "search", Job.created_at >= start)
        )
    ).scalar_one()
    usage = await monthly_usage(session, runtime.pricing, now)

    callbacks = (
        (
            await session.execute(
                select(Business)
                .where(
                    Business.next_callback_at.is_not(None),
                    Business.next_callback_at < day_end,
                    Business.suppressed.is_(False),
                )
                .order_by(Business.next_callback_at.asc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    # The best deals nobody has called yet.
    top_hot = (
        (
            await session.execute(
                select(Business)
                .where(
                    *callable_conditions(),
                    Business.call_count == 0,
                    Business.lead_category.in_(sellable),
                )
                .order_by(Business.expected_value.desc(), Business.opportunity_score.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    recent_jobs = (
        (
            await session.execute(
                select(Job).where(Job.kind == "search").order_by(Job.created_at.desc()).limit(6)
            )
        )
        .scalars()
        .all()
    )

    return {
        "kpis": {
            "total_leads": kpis[0],
            "hot_leads": kpis[1],
            "warm_leads": kpis[2],
            "no_website": kpis[3],
            "website_problems": kpis[4],
            "google_opportunities": kpis[5],
            "phones_found": kpis[6],
            "contacted": kpis[7],
            "interested": kpis[8],
            "callbacks_due": kpis[9],
            "suppressed": kpis[10],
            "demo_records": kpis[11],
            "calls_today": calls_today,
        },
        "goal": {
            "weekly_goal": runtime.offers.weekly_goal,
            "calls_per_day": runtime.offers.calls_per_day,
            "won_value_7d": int(won[0]),
            "won_count_7d": int(won[1]),
            "in_play_value": int(playing[0]),
            "in_play_count": int(playing[1]),
            "calls_7d": int(calls_7d),
            "ready_leads": sum(r[0] for r in ready),
            "ready_expected_value": sum(r[2] for r in ready),
        },
        "by_category": by_category,
        "by_opportunity": by_opportunity,
        "calls_by_outcome": sorted(
            [{"key": str(k), "count": int(v)} for k, v in outcome_rows], key=lambda x: -x["count"]
        ),
        "pipeline": pipeline,
        "by_priority": {str(k): int(v) for k, v in priority_rows},
        "month": {
            "period_start": start.isoformat(),
            "searches": searches_month,
            "businesses": month[0],
            "phone_numbers": month[1],
            "website_audits": audits_month,
            "api_calls": usage["api_calls"],
            "cached_calls": usage["cached_calls"],
            "cost": usage["cost"],
        },
        "callbacks": [to_summary(b).model_dump(mode="json") for b in callbacks],
        "top_hot": [to_summary(b).model_dump(mode="json") for b in top_hot],
        "recent_jobs": [
            {
                "id": j.id,
                "status": j.status,
                "params": j.params,
                "progress_processed": j.progress_processed,
                "progress_total": j.progress_total,
                "counters": j.counters,
                "created_at": j.created_at.isoformat(),
            }
            for j in recent_jobs
        ],
    }
