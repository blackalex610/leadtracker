from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.enums import CallOutcome, DataQuality, LeadStatus, OpportunityType, Priority
from app.schemas.common import ORMModel


class ScoreReason(BaseModel):
    rule: str | None
    points: int
    text: str
    opportunity: OpportunityType | None = None
    tier: str


class LeadSummary(ORMModel):
    id: int
    name: str
    category: str | None
    city: str | None
    neighborhood: str | None
    address: str | None
    international_phone: str | None
    national_phone: str | None
    normalized_phone: str | None
    phone_invalid: bool
    rating: float | None
    review_count: int | None
    website_url: str | None
    website_kind: str | None
    website_status: str
    website_health_score: int | None
    outdated_score: int | None
    opportunity_score: int
    priority: Priority
    opportunity_types: list[OpportunityType]
    top_reason: str | None = None
    status: LeadStatus
    suppressed: bool
    is_demo: bool
    data_quality: DataQuality
    google_maps_url: str | None
    business_status: str | None
    open_in_calling_window: bool | None
    assigned_to_id: int | None
    last_contacted_at: datetime | None
    next_callback_at: datetime | None
    call_count: int
    created_at: datetime


class ContactOut(ORMModel):
    id: int
    raw_phone: str
    normalized_phone: str
    national_format: str | None
    international_format: str | None
    country_code: int | None
    phone_type: str | None
    phone_source: str
    phone_verified: bool
    verification_method: str | None
    is_primary: bool
    invalid: bool


class AuditOut(ORMModel):
    id: int
    url: str
    final_url: str | None
    status: str
    error_code: str | None
    error_message: str | None
    http_status: int | None
    https: bool | None
    redirect_count: int
    redirect_chain: list[dict[str, Any]]
    response_time_ms: int | None
    health_score: int | None
    outdated_score: int | None
    outdated_band: str | None
    category_scores: dict[str, Any]
    signals: list[dict[str, Any]]
    outdated_signals: list[dict[str, Any]]
    facts: dict[str, Any]
    pages: list[dict[str, Any]]
    analyzer_version: str
    started_at: datetime
    finished_at: datetime | None


class CallOut(ORMModel):
    id: int
    outcome: CallOutcome
    note: str | None
    phone_dialed: str | None
    callback_at: datetime | None
    user_id: int | None
    user_name: str | None = None
    session_id: int | None
    created_at: datetime


class NoteOut(ORMModel):
    id: int
    body: str
    user_id: int | None
    user_name: str | None = None
    created_at: datetime


class EventOut(ORMModel):
    id: int
    type: str
    data: dict[str, Any]
    user_id: int | None
    created_at: datetime


class SourceOut(ORMModel):
    provider: str
    external_id: str
    match_reason: str | None
    first_seen_at: datetime
    last_seen_at: datetime


class PitchOut(BaseModel):
    language: str
    text: str
    primary_opportunity: str | None
    talking_points: list[str]


class UserRef(ORMModel):
    id: int
    name: str
    email: str


class LeadDetail(LeadSummary):
    primary_type: str | None
    types: list[str]
    niche_key: str | None
    niche_label: str | None = None
    subcategory: str | None
    description: str | None
    postal_code: str | None
    country_code: str | None
    latitude: float | None
    longitude: float | None
    opening_hours: dict[str, Any] | None
    utc_offset_minutes: int | None
    photo_count: int | None
    google_profile_score: int | None
    google_signals: list[dict[str, Any]]
    score_reasons: list[ScoreReason]
    priority_reason: str | None
    strong_category: bool
    booking_oriented: bool
    provider: str
    provider_place_id: str | None
    source_timestamp: datetime | None
    phone_raw: str | None
    phone_type: str | None
    phone_source: str | None
    phone_verified: bool
    last_audited_at: datetime | None
    data_quality_checklist: dict[str, bool] = Field(default_factory=dict)
    contacts: list[ContactOut] = Field(default_factory=list)
    audit: AuditOut | None = None
    pitches: dict[str, PitchOut] = Field(default_factory=dict)
    calls: list[CallOut] = Field(default_factory=list)
    notes: list[NoteOut] = Field(default_factory=list)
    events: list[EventOut] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    assigned_to: UserRef | None = None
    created_by: UserRef | None = None
    last_contacted_by: UserRef | None = None
    open_today_in_window: bool | None = None
    active_job_id: int | None = None


class LeadUpdate(BaseModel):
    status: LeadStatus | None = None
    assigned_to_id: int | None = None
    unassign: bool = False
    next_callback_at: datetime | None = None
    niche_key: str | None = None
    website_url: str | None = Field(default=None, max_length=1000)
    add_phone: str | None = Field(default=None, max_length=64)
    confirm_reenable: bool = False


class BulkLeadUpdate(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    status: LeadStatus | None = None
    assigned_to_id: int | None = None
    unassign: bool = False


class BulkResult(BaseModel):
    updated: int
    skipped: int = 0


class CallCreate(BaseModel):
    outcome: CallOutcome
    note: str | None = Field(default=None, max_length=5000)
    callback_at: datetime | None = None
    session_id: int | None = None


class CallResult(BaseModel):
    call: CallOut
    status: LeadStatus
    suppressed: bool
    next_callback_at: datetime | None


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class JobRef(BaseModel):
    job_id: int
    status: str


class AuditRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)
    force: bool = True


SortField = Literal[
    "priority",
    "opportunity_score",
    "website_score",
    "review_count",
    "rating",
    "name",
    "created_at",
    "last_contacted_at",
    "next_callback_at",
]
