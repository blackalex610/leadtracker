"""Night-calling sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.models import CallAttempt, CallingSession
from app.schemas.misc import (
    CallingFilters,
    CallingPreview,
    CallingSessionOut,
    CallingSessionSummary,
    CallingSessionUpdate,
)
from app.services.calling import build_cards, build_queue, create_session, session_stats
from app.services.leads import to_summary
from app.services.settings import load_settings

router = APIRouter(prefix="/calling-sessions", tags=["calling"])


async def _session_or_404(session: SessionDep, session_id: int) -> CallingSession:
    calling = await session.get(CallingSession, session_id)
    if calling is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Calling session not found"}
        )
    return calling


async def _out(session: SessionDep, calling: CallingSession) -> CallingSessionOut:
    runtime = await load_settings(session)
    filters = CallingFilters.model_validate(calling.filters or {})
    cards = await build_cards(session, list(calling.lead_ids or []), runtime, filters)
    return CallingSessionOut(
        id=calling.id,
        filters=calling.filters,
        lead_ids=list(calling.lead_ids or []),
        position=calling.position,
        started_at=calling.started_at,
        ended_at=calling.ended_at,
        stats=await session_stats(session, calling.id),
        cards=cards,
    )


@router.post("/preview", response_model=CallingPreview)
async def preview(filters: CallingFilters, session: SessionDep, user: CurrentUser) -> CallingPreview:
    runtime = await load_settings(session)
    queue = await build_queue(session, filters, runtime, user.id)
    return CallingPreview(count=len(queue), sample=[to_summary(b) for b in queue[:5]])


@router.post("", response_model=CallingSessionOut, status_code=status.HTTP_201_CREATED)
async def start(filters: CallingFilters, session: SessionDep, user: CurrentUser) -> CallingSessionOut:
    runtime = await load_settings(session)
    calling = await create_session(session, filters, runtime, user.id)
    if not calling.lead_ids:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_queue", "message": "No callable leads match these filters."},
        )
    await session.commit()
    await session.refresh(calling)
    return await _out(session, calling)


@router.get("", response_model=list[CallingSessionSummary])
async def list_sessions(
    session: SessionDep, _user: CurrentUser, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[CallingSessionSummary]:
    rows = (
        (
            await session.execute(
                select(CallingSession).order_by(CallingSession.started_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    ids = [r.id for r in rows]
    counts: dict[int, dict[str, int]] = {}
    if ids:
        for sid, outcome, count in (
            await session.execute(
                select(CallAttempt.session_id, CallAttempt.outcome, func.count())
                .where(CallAttempt.session_id.in_(ids))
                .group_by(CallAttempt.session_id, CallAttempt.outcome)
            )
        ).all():
            counts.setdefault(int(sid), {})[str(outcome)] = int(count)
    return [
        CallingSessionSummary(
            id=r.id,
            started_at=r.started_at,
            ended_at=r.ended_at,
            total=len(r.lead_ids or []),
            position=r.position,
            stats={**counts.get(r.id, {}), "total_calls": sum(counts.get(r.id, {}).values())},
            filters=r.filters,
        )
        for r in rows
    ]


@router.get("/{session_id}", response_model=CallingSessionOut)
async def get_session_detail(session_id: int, session: SessionDep, _user: CurrentUser) -> CallingSessionOut:
    return await _out(session, await _session_or_404(session, session_id))


@router.patch("/{session_id}", response_model=CallingSessionSummary)
async def update_position(
    session_id: int, body: CallingSessionUpdate, session: SessionDep, _user: CurrentUser
) -> CallingSessionSummary:
    calling = await _session_or_404(session, session_id)
    calling.position = min(body.position, max(0, len(calling.lead_ids or [])))
    await session.commit()
    return CallingSessionSummary(
        id=calling.id,
        started_at=calling.started_at,
        ended_at=calling.ended_at,
        total=len(calling.lead_ids or []),
        position=calling.position,
        stats=await session_stats(session, calling.id),
        filters=calling.filters,
    )


@router.post("/{session_id}/end", response_model=CallingSessionSummary)
async def end_session(session_id: int, session: SessionDep, _user: CurrentUser) -> CallingSessionSummary:
    calling = await _session_or_404(session, session_id)
    calling.ended_at = calling.ended_at or datetime.now(UTC)
    await session.commit()
    return CallingSessionSummary(
        id=calling.id,
        started_at=calling.started_at,
        ended_at=calling.ended_at,
        total=len(calling.lead_ids or []),
        position=calling.position,
        stats=await session_stats(session, calling.id),
        filters=calling.filters,
    )
