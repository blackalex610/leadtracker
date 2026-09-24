"""Health, meta, auth and users endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, text

from app.api.deps import CurrentUser, SessionDep
from app.audit.signals import SIGNAL_CATALOG
from app.config import get_settings
from app.core.enums import OPPORTUNITY_LABELS, CallOutcome, LeadStatus
from app.core.ratelimit import login_limiter, rate_limit
from app.core.security import hash_token, sign_session
from app.data.locations import CATEGORY_SUGGESTIONS, CITIES
from app.models import User
from app.providers.registry import provider_status
from app.schemas.common import OkResponse
from app.schemas.misc import LoginRequest, MeResponse, MetaOut, ProviderStatusOut, UserOut
from app.scoring.config import RULE_META

router = APIRouter()


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["system"])
async def ready(session: SessionDep) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail={"code": "db_unavailable", "message": "Database unavailable"}
        ) from exc
    return {"status": "ready"}


@router.get("/meta", response_model=MetaOut, tags=["system"])
async def meta(_user: CurrentUser) -> MetaOut:
    settings = get_settings()
    return MetaOut(
        version=settings.app_version,
        environment=settings.environment,
        auth_mode=settings.auth_mode,
        provider=ProviderStatusOut(**provider_status(settings)),
        pagespeed_configured=settings.pagespeed_api_key is not None,
        cities=CITIES,
        category_suggestions=CATEGORY_SUGGESTIONS,
        lead_statuses=list(LeadStatus),
        call_outcomes=[o.value for o in CallOutcome],
        opportunity_labels={k.value: v for k, v in OPPORTUNITY_LABELS.items()},
        rule_meta={k.value: v.model_dump(mode="json") for k, v in RULE_META.items()},
        signal_catalog={
            code: {
                "category": s.category,
                "severity": s.severity.value,
                "label": s.label,
                "penalty": s.penalty,
            }
            for code, s in SIGNAL_CATALOG.items()
        },
    )


@router.post(
    "/auth/login",
    response_model=MeResponse,
    tags=["auth"],
    dependencies=[Depends(rate_limit(login_limiter, "login"))],
)
async def login(body: LoginRequest, response: Response, session: SessionDep) -> MeResponse:
    settings = get_settings()
    if settings.auth_mode != "token":
        raise HTTPException(
            status_code=400, detail={"code": "auth_disabled", "message": "Authentication is disabled."}
        )
    user = (
        await session.execute(select(User).where(User.token_hash == hash_token(body.token.strip())))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401, detail={"code": "invalid_token", "message": "Invalid access token."}
        )
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    response.set_cookie(
        settings.session_cookie_name,
        sign_session(user.id),
        max_age=settings.session_max_age_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return MeResponse(user=UserOut.model_validate(user), auth_mode=settings.auth_mode)


@router.post("/auth/logout", response_model=OkResponse, tags=["auth"])
async def logout(response: Response) -> OkResponse:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return OkResponse()


@router.get("/auth/me", response_model=MeResponse, tags=["auth"])
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(user=UserOut.model_validate(user), auth_mode=get_settings().auth_mode)


@router.get("/users", response_model=list[UserOut], tags=["users"])
async def list_users(session: SessionDep, _user: CurrentUser) -> list[UserOut]:
    users = (
        await session.execute(select(User).where(User.is_active.is_(True)).order_by(User.name))
    ).scalars()
    return [UserOut.model_validate(u) for u in users]
