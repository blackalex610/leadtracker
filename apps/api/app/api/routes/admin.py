"""Settings, usage, niche presets and the suppression list."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.config import get_settings
from app.core.enums import JobKind
from app.core.phone import normalize_phone
from app.models import Business, NichePreset, SuppressionEntry
from app.providers.registry import provider_status
from app.schemas.common import OkResponse
from app.schemas.dashboard import SettingsOut, UsageOut
from app.schemas.leads import JobRef
from app.schemas.misc import PresetCreate, PresetOut, PresetUpdate, SuppressionCreate, SuppressionOut
from app.services.presets import preset_usage
from app.services.settings import RuntimeSettings, load_settings, update_settings
from app.services.suppression import reenable, suppress
from app.services.usage import monthly_usage
from app.worker.queue import enqueue

router = APIRouter()


def _settings_payload(runtime: RuntimeSettings) -> SettingsOut:
    env = get_settings()
    return SettingsOut.model_validate(
        {
            "runtime": runtime,
            "environment": {
                "provider": provider_status(env),
                "provider_api_key_set": env.provider_api_key is not None,
                "pagespeed_api_key_set": env.pagespeed_api_key is not None,
                "places_field_tier": env.places_field_tier,
                "demo_mode": env.demo_mode,
                "auth_mode": env.auth_mode,
                "environment": env.environment,
                "google_latlng_retention_days": env.google_latlng_retention_days,
            },
        }
    )


@router.get("/settings", response_model=SettingsOut, tags=["settings"])
async def get_app_settings(session: SessionDep, _user: CurrentUser) -> SettingsOut:
    return _settings_payload(await load_settings(session, use_cache=False))


@router.patch("/settings", response_model=SettingsOut, tags=["settings"])
async def patch_app_settings(
    patch: dict[str, dict[str, Any]], session: SessionDep, user: CurrentUser
) -> SettingsOut:
    forbidden = {"provider_api_key", "api_key", "secret", "token"}
    for values in patch.values():
        if not isinstance(values, dict) or forbidden & {k.lower() for k in values}:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_settings",
                    "message": "Secrets are configured via environment variables",
                },
            )
    try:
        runtime = await update_settings(session, patch, user.id)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_settings", "message": exc.errors()[0].get("msg", "Invalid settings")},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_settings", "message": str(exc)}
        ) from exc
    return _settings_payload(runtime)


@router.post(
    "/settings/rescore", response_model=JobRef, status_code=status.HTTP_202_ACCEPTED, tags=["settings"]
)
async def rescore_all(session: SessionDep, user: CurrentUser) -> JobRef:
    job = await enqueue(session, JobKind.RESCORE, {}, created_by_id=user.id)
    await session.commit()
    return JobRef(job_id=job.id, status=job.status)


@router.get("/usage", response_model=UsageOut, tags=["settings"])
async def usage(session: SessionDep, _user: CurrentUser) -> UsageOut:
    runtime = await load_settings(session)
    return UsageOut.model_validate(await monthly_usage(session, runtime.pricing))


# --- presets -------------------------------------------------------------------------------------
@router.get("/presets", response_model=list[PresetOut], tags=["presets"])
async def list_presets(session: SessionDep, _user: CurrentUser) -> list[PresetOut]:
    usage_counts = await preset_usage(session)
    presets = (
        await session.execute(select(NichePreset).order_by(NichePreset.sort_order, NichePreset.id))
    ).scalars()
    return [
        PresetOut.model_validate(p).model_copy(update={"lead_count": usage_counts.get(p.key, 0)})
        for p in presets
    ]


@router.post("/presets", response_model=PresetOut, status_code=status.HTTP_201_CREATED, tags=["presets"])
async def create_preset(body: PresetCreate, session: SessionDep, _user: CurrentUser) -> PresetOut:
    exists = (await session.execute(select(NichePreset.id).where(NichePreset.key == body.key))).first()
    if exists:
        raise HTTPException(
            status_code=409, detail={"code": "duplicate", "message": "A preset with this key exists"}
        )
    preset = NichePreset(**body.model_dump(mode="json"), is_builtin=False)
    session.add(preset)
    await session.commit()
    await session.refresh(preset)
    return PresetOut.model_validate(preset)


@router.patch("/presets/{preset_id}", response_model=PresetOut, tags=["presets"])
async def update_preset(
    preset_id: int, body: PresetUpdate, session: SessionDep, _user: CurrentUser
) -> PresetOut:
    preset = await session.get(NichePreset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Preset not found"})
    for key, value in body.model_dump(mode="json", exclude_unset=True).items():
        setattr(preset, key, value)
    await session.commit()
    await session.refresh(preset)
    return PresetOut.model_validate(preset)


@router.delete("/presets/{preset_id}", response_model=OkResponse, tags=["presets"])
async def delete_preset(preset_id: int, session: SessionDep, _user: CurrentUser) -> OkResponse:
    preset = await session.get(NichePreset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Preset not found"})
    await session.delete(preset)
    await session.commit()
    return OkResponse()


# --- suppression -----------------------------------------------------------------------------------
@router.get("/suppression", response_model=list[SuppressionOut], tags=["suppression"])
async def list_suppression(
    session: SessionDep, _user: CurrentUser, include_inactive: bool = False
) -> list[SuppressionOut]:
    stmt = select(SuppressionEntry).order_by(SuppressionEntry.created_at.desc()).limit(2000)
    if not include_inactive:
        stmt = stmt.where(SuppressionEntry.active.is_(True))
    return [SuppressionOut.model_validate(e) for e in (await session.execute(stmt)).scalars()]


@router.post(
    "/suppression", response_model=SuppressionOut, status_code=status.HTTP_201_CREATED, tags=["suppression"]
)
async def add_suppression(body: SuppressionCreate, session: SessionDep, user: CurrentUser) -> SuppressionOut:
    runtime = await load_settings(session)
    phone = None
    if body.phone:
        normalized = normalize_phone(body.phone, runtime.general.default_country)
        if normalized is None:
            raise HTTPException(
                status_code=422, detail={"code": "invalid_phone", "message": "Phone number is not valid"}
            )
        phone = normalized.e164
    business_id = body.business_id
    if business_id is not None:
        business = await session.get(Business, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Lead not found"})
        phone = phone or business.normalized_phone
    if not phone and business_id is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "phone_or_lead_required", "message": "Provide a phone number or a lead"},
        )
    entry = await suppress(
        session, normalized_phone=phone, business_id=business_id, reason=body.reason, user_id=user.id
    )
    await session.commit()
    await session.refresh(entry)
    return SuppressionOut.model_validate(entry)


@router.delete("/suppression/{entry_id}", response_model=SuppressionOut, tags=["suppression"])
async def reenable_suppression(entry_id: int, session: SessionDep, user: CurrentUser) -> SuppressionOut:
    """Explicitly re-enable a suppressed number (the entry is kept, deactivated)."""
    entry = await session.get(SuppressionEntry, entry_id)
    if entry is None or not entry.active:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Active entry not found"}
        )
    await reenable(session, entry, user.id)
    await session.commit()
    await session.refresh(entry)
    return SuppressionOut.model_validate(entry)
