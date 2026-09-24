"""Dashboard, CSV export and CSV import."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.enums import JobKind
from app.core.ratelimit import import_limiter, rate_limit
from app.log import get_logger
from app.models import Business, ImportBatch
from app.schemas.dashboard import DashboardOut
from app.schemas.misc import ImportCommit, ImportPreview, ImportPreviewRow, ImportResult
from app.services import csv_import
from app.services.csv_export import export_rows
from app.services.dashboard import dashboard
from app.services.leads import LeadExportQuery, apply_filters
from app.services.presets import load_niches
from app.services.scoring_service import rescore_business
from app.services.settings import load_settings
from app.worker.queue import enqueue

router = APIRouter()
log = get_logger(__name__)


@router.get("/dashboard", response_model=DashboardOut, tags=["dashboard"])
async def get_dashboard(session: SessionDep, _user: CurrentUser) -> DashboardOut:
    runtime = await load_settings(session)
    return DashboardOut.model_validate(await dashboard(session, runtime))


@router.get("/export", tags=["export"], response_class=StreamingResponse)
async def export_csv(
    session: SessionDep, user: CurrentUser, query: Annotated[LeadExportQuery, Query()]
) -> StreamingResponse:
    filters, sort, order = query, query.sort, query.order
    runtime = await load_settings(session)
    total = (
        await session.execute(
            select(func.count()).select_from(apply_filters(select(Business), filters, user.id).subquery())
        )
    ).scalar_one()
    log.info("export_created", rows=total, user_id=user.id)
    filename = f"leads-{datetime.now(UTC):%Y%m%d-%H%M}.csv"
    return StreamingResponse(
        export_rows(
            session,
            filters,
            sort=sort,
            order=order,
            delimiter=runtime.csv.delimiter,
            include_bom=runtime.csv.include_bom,
            user_id=user.id,
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Total-Count": str(total)},
    )


def _preview_from_batch(
    batch: ImportBatch, rows: list[csv_import.ParsedRow], dupes: dict[int, csv_import.DuplicateInfo]
) -> ImportPreview:
    preview_rows: list[ImportPreviewRow] = []
    counts = {"new": 0, "duplicate": 0, "invalid": 0}
    for row in rows:
        dup = dupes.get(row.index)
        state = "invalid" if not row.valid else ("duplicate" if dup else "new")
        counts[state] += 1
        if len(preview_rows) < csv_import.PREVIEW_ROWS:
            preview_rows.append(
                ImportPreviewRow(
                    index=row.index,
                    values=row.values,
                    status=state,
                    duplicate_of=dup.business_id if dup else None,
                    duplicate_name=dup.business_name if dup else None,
                    match_reason=dup.reason if dup else None,
                    issues=row.issues,
                )
            )
    return ImportPreview(
        batch_id=batch.id,
        filename=batch.filename,
        columns=batch.columns,
        mapping=batch.mapping,
        total_rows=len(rows),
        counts=counts,
        rows=preview_rows,
        target_fields=csv_import.TARGET_FIELDS,
    )


@router.post(
    "/import/preview",
    response_model=ImportPreview,
    tags=["import"],
    dependencies=[Depends(rate_limit(import_limiter, "import"))],
)
async def import_preview(
    session: SessionDep, user: CurrentUser, file: UploadFile = File(...)
) -> ImportPreview:
    data = await file.read(csv_import.MAX_BYTES + 1)
    try:
        text = csv_import.decode_csv(data)
        columns, raw_rows = csv_import.parse_csv(text)
    except csv_import.ImportError_ as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_csv", "message": str(exc)}) from exc
    mapping = csv_import.guess_mapping(columns)
    batch = ImportBatch(
        filename=(file.filename or "import.csv")[:255],
        columns=columns,
        rows=raw_rows,
        mapping=mapping,
        created_by_id=user.id,
    )
    session.add(batch)
    await session.commit()
    await session.refresh(batch)
    runtime = await load_settings(session)
    rows = csv_import.extract_rows(columns, raw_rows, mapping, runtime.general.default_country)
    dupes = await csv_import.detect_duplicates(session, rows)
    return _preview_from_batch(batch, rows, dupes)


@router.post("/import/remap", response_model=ImportPreview, tags=["import"])
async def import_remap(body: ImportCommit, session: SessionDep, user: CurrentUser) -> ImportPreview:
    batch = await session.get(ImportBatch, body.batch_id)
    if batch is None or batch.status != "preview":
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Import batch not found"}
        )
    if body.mapping:
        batch.mapping = {k: v for k, v in body.mapping.items() if k in csv_import.TARGET_FIELDS}
        await session.commit()
    runtime = await load_settings(session)
    rows = csv_import.extract_rows(batch.columns, batch.rows, batch.mapping, runtime.general.default_country)
    dupes = await csv_import.detect_duplicates(session, rows)
    return _preview_from_batch(batch, rows, dupes)


@router.post(
    "/import",
    response_model=ImportResult,
    tags=["import"],
    dependencies=[Depends(rate_limit(import_limiter, "import"))],
)
async def import_commit(body: ImportCommit, session: SessionDep, user: CurrentUser) -> ImportResult:
    batch = await session.get(ImportBatch, body.batch_id)
    if batch is None or batch.status != "preview":
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Import batch not found"}
        )
    mapping = {k: v for k, v in (body.mapping or batch.mapping).items() if k in csv_import.TARGET_FIELDS}
    if not mapping.get("name"):
        raise HTTPException(
            status_code=422, detail={"code": "name_required", "message": "Map a column to 'name'"}
        )
    runtime = await load_settings(session)
    rows = csv_import.extract_rows(batch.columns, batch.rows, mapping, runtime.general.default_country)
    dupes = await csv_import.detect_duplicates(session, rows)
    counts, touched = await csv_import.commit_rows(
        session,
        rows,
        dupes,
        strategy=body.duplicate_strategy,
        skip_rows=set(body.skip_rows),
        default_region=runtime.general.default_country,
        user_id=user.id,
    )
    niches = await load_niches(session)
    businesses = (await session.execute(select(Business).where(Business.id.in_(touched)))).scalars().all()
    for business in businesses:
        await rescore_business(session, business, runtime, niches)
    audit_job_id = None
    to_audit = [
        b.id
        for b in businesses
        if b.website_url and b.website_kind == "own" and b.website_status == "unaudited"
    ]
    if body.audit_websites and to_audit:
        job = await enqueue(
            session, JobKind.AUDIT, {"business_ids": to_audit, "force": False}, created_by_id=user.id
        )
        audit_job_id = job.id
    batch.status = "committed"
    batch.mapping = mapping
    batch.result = counts
    batch.rows = []  # drop raw rows once imported
    await session.commit()
    log.info("import_committed", **counts, audit_job_id=audit_job_id)
    return ImportResult(**counts, audit_job_id=audit_job_id)
