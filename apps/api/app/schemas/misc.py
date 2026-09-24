from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.core.enums import LeadStatus, OpportunityType, Priority
from app.core.opening_hours import parse_hhmm
from app.schemas.common import ORMModel, Schema
from app.schemas.leads import LeadSummary, PitchOut, ScoreReason


# --- users / auth -------------------------------------------------------------------
class UserOut(ORMModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class LoginRequest(Schema):
    token: str = Field(min_length=10, max_length=200)


class MeResponse(Schema):
    user: UserOut
    auth_mode: str


# --- presets --------------------------------------------------------------------------
class PresetBase(Schema):
    label: str = Field(min_length=1, max_length=120)
    label_bg: str | None = Field(default=None, max_length=120)
    category_query: str = Field(min_length=2, max_length=200)
    included_type: str | None = Field(default=None, max_length=100)
    keywords: str | None = Field(default=None, max_length=300)
    match_types: list[str] = Field(default_factory=list, max_length=30)
    calling_window_start: str | None = None
    calling_window_end: str | None = None
    booking_oriented: bool = False
    discovery_dependent: bool = True
    strong_opportunities: list[OpportunityType] = Field(default_factory=list)
    sort_order: int = 100

    @field_validator("calling_window_start", "calling_window_end")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v:
            parse_hhmm(v)
            return v.zfill(5)
        return None


class PresetCreate(PresetBase):
    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")


class PresetUpdate(Schema):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    label_bg: str | None = None
    category_query: str | None = Field(default=None, min_length=2, max_length=200)
    included_type: str | None = None
    keywords: str | None = None
    match_types: list[str] | None = None
    calling_window_start: str | None = None
    calling_window_end: str | None = None
    booking_oriented: bool | None = None
    discovery_dependent: bool | None = None
    strong_opportunities: list[OpportunityType] | None = None
    sort_order: int | None = None


class PresetOut(ORMModel, PresetBase):
    id: int
    key: str
    is_builtin: bool
    lead_count: int = 0


# --- suppression ------------------------------------------------------------------------
class SuppressionCreate(Schema):
    phone: str | None = Field(default=None, max_length=64)
    business_id: int | None = None
    reason: str | None = Field(default=None, max_length=1000)


class SuppressionOut(ORMModel):
    id: int
    normalized_phone: str | None
    business_id: int | None
    reason: str | None
    active: bool
    created_by_id: int | None
    created_at: datetime
    deactivated_at: datetime | None


# --- calling -------------------------------------------------------------------------------
class CallingFilters(Schema):
    niche_key: str | None = None
    category: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    window_start: str | None = None
    window_end: str | None = None
    open_today: bool = True
    priorities: list[Priority] = Field(default_factory=lambda: [Priority.HOT, Priority.WARM])
    website: Literal["any", "none", "poor"] = "any"
    opportunity_types: list[OpportunityType] = Field(default_factory=list)
    statuses: list[LeadStatus] = Field(
        default_factory=lambda: [LeadStatus.NEW, LeadStatus.NO_ANSWER, LeadStatus.CALLBACK]
    )
    min_score: int | None = Field(default=None, ge=0, le=100)
    limit: int = Field(default=50, ge=1, le=500)
    include_unknown_hours: bool | None = None
    assigned_to_me: bool = False

    @field_validator("window_start", "window_end")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v:
            parse_hhmm(v)
        return v


class CallingCard(Schema):
    lead: LeadSummary
    reasons: list[ScoreReason]
    pitch: PitchOut | None
    hours_today: str | None
    open_in_window_today: bool | None
    website_summary: str | None
    last_call_outcome: str | None
    last_call_at: datetime | None
    last_note: str | None
    callable: bool
    not_callable_reason: str | None


class CallingSessionOut(Schema):
    id: int
    filters: dict[str, Any]
    lead_ids: list[int]
    position: int
    started_at: datetime
    ended_at: datetime | None
    stats: dict[str, int]
    cards: list[CallingCard]


class CallingSessionSummary(Schema):
    id: int
    started_at: datetime
    ended_at: datetime | None
    total: int
    position: int
    stats: dict[str, int]
    filters: dict[str, Any]


class CallingPreview(Schema):
    count: int
    sample: list[LeadSummary]


class CallingSessionUpdate(Schema):
    position: int = Field(ge=0)


# --- import --------------------------------------------------------------------------------
class ImportPreviewRow(Schema):
    index: int
    values: dict[str, str | None]
    status: Literal["new", "duplicate", "invalid"]
    duplicate_of: int | None = None
    duplicate_name: str | None = None
    match_reason: str | None = None
    issues: list[str] = Field(default_factory=list)


class ImportPreview(Schema):
    batch_id: int
    filename: str
    columns: list[str]
    mapping: dict[str, str | None]
    total_rows: int
    counts: dict[str, int]
    rows: list[ImportPreviewRow]
    target_fields: list[str]


class ImportCommit(Schema):
    batch_id: int
    mapping: dict[str, str | None] | None = None
    duplicate_strategy: Literal["skip", "fill_empty"] = "skip"
    audit_websites: bool = True
    skip_rows: list[int] = Field(default_factory=list)


class ImportResult(Schema):
    created: int
    merged: int
    skipped_duplicates: int
    invalid: int
    audit_job_id: int | None


# --- meta ------------------------------------------------------------------------------------
class ProviderStatusOut(Schema):
    name: str
    configured: bool
    demo_mode: bool
    field_tier: str | None


class WorkerRunOut(Schema):
    ran: int
    queued: int
    running: int
    on_demand: bool


class MetaOut(Schema):
    version: str
    environment: str
    auth_mode: str
    on_demand_worker: bool
    provider: ProviderStatusOut
    pagespeed_configured: bool
    cities: dict[str, list[str]]
    category_suggestions: list[str]
    lead_statuses: list[LeadStatus]
    call_outcomes: list[str]
    opportunity_labels: dict[str, str]
    rule_meta: dict[str, dict[str, Any]]
    signal_catalog: dict[str, dict[str, Any]]
