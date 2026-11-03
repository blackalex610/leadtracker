from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.common import Schema
from app.schemas.leads import LeadSummary
from app.services.settings import RuntimeSettings


class DashboardKpis(Schema):
    total_leads: int
    hot_leads: int
    warm_leads: int
    no_website: int
    website_problems: int
    google_opportunities: int
    phones_found: int
    contacted: int
    interested: int
    callbacks_due: int
    suppressed: int
    demo_records: int
    calls_today: int


class KeyCount(Schema):
    key: str
    count: int


class OpportunityCount(KeyCount):
    label: str


class CostLine(Schema):
    sku: str
    units: int
    billable_units: int
    free_units: int | None = None
    price_per_1000: float | None = None
    cost: float | None
    priced: bool


class CostEstimate(Schema):
    currency: str
    total: float
    display_currency: str
    display_total: float
    exchange_rate: float
    lines: list[CostLine]


class UsageOut(Schema):
    period_start: str
    api_calls: int
    cached_calls: int
    calls_by_operation: dict[str, int]
    cost: CostEstimate


class MonthSummary(Schema):
    period_start: str
    searches: int
    businesses: int
    phone_numbers: int
    website_audits: int
    api_calls: int
    cached_calls: int
    cost: CostEstimate


class CategoryCount(Schema):
    key: str
    label: str
    count: int
    deal_value: int
    expected_value: int


class GoalProgress(Schema):
    weekly_goal: int
    calls_per_day: int
    won_value_7d: int
    won_count_7d: int
    in_play_value: int
    in_play_count: int
    calls_7d: int
    ready_leads: int
    ready_expected_value: int


class RecentJob(Schema):
    id: int
    status: str
    params: dict[str, Any]
    progress_processed: int
    progress_total: int
    counters: dict[str, Any]
    created_at: datetime


class DashboardOut(Schema):
    kpis: DashboardKpis
    goal: GoalProgress
    by_category: list[CategoryCount]
    by_opportunity: list[OpportunityCount]
    calls_by_outcome: list[KeyCount]
    pipeline: list[KeyCount]
    by_priority: dict[str, int]
    month: MonthSummary
    callbacks: list[LeadSummary]
    top_hot: list[LeadSummary]
    recent_jobs: list[RecentJob]


class FacetValue(Schema):
    value: str
    count: int


class FacetsOut(Schema):
    categories: list[FacetValue]
    cities: list[FacetValue]
    targets: list[FacetValue]
    lead_categories: list[FacetValue]


class ProviderInfo(Schema):
    name: str
    configured: bool
    demo_mode: bool
    field_tier: str | None


class EnvironmentInfo(Schema):
    provider: ProviderInfo
    provider_api_key_set: bool
    pagespeed_api_key_set: bool
    places_field_tier: str
    demo_mode: bool
    auth_mode: str
    environment: str
    google_latlng_retention_days: int


class SettingsOut(Schema):
    runtime: RuntimeSettings
    environment: EnvironmentInfo
