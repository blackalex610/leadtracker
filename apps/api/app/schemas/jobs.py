from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.core.enums import JobStatus
from app.schemas.common import ORMModel


class JobOut(ORMModel):
    id: int
    kind: str
    status: JobStatus
    params: dict[str, Any]
    stage: str | None
    progress_total: int
    progress_processed: int
    counters: dict[str, Any]
    errors: list[dict[str, Any]]
    error_code: str | None
    error_message: str | None
    cancel_requested: bool
    attempts: int
    retry_of_id: int | None
    created_by_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SearchQueryOut(ORMModel):
    id: int
    text_query: str
    pages_fetched: int
    results_count: int
    cached: bool
    status: str
    error_code: str | None
    error_message: str | None
    created_at: datetime


class SearchJobDetail(JobOut):
    queries: list[SearchQueryOut] = []


class SearchEstimate(BaseModel):
    queries: int
    max_requests: int
    sku: str | None
    estimated_max_cost: float | None
    currency: str
    display_currency: str
    estimated_max_cost_display: float | None
    free_units_remaining: int | None
    provider_configured: bool
    demo_mode: bool
