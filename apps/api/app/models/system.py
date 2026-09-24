from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ApiUsage(Base):
    """One provider request (or cache hit). Cost is computed from units and the
    configurable pricing table at read time, never stored."""

    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    operation: Mapped[str] = mapped_column(String(40))
    sku: Mapped[str | None] = mapped_column(String(60))
    units: Mapped[int] = mapped_column(Integer, default=1)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    error_code: Mapped[str | None] = mapped_column(String(40))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ProviderCache(Base):
    __tablename__ = "provider_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    operation: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class NichePreset(TimestampMixin, Base):
    """Reusable search/calling template ("GYMS", "BEAUTY", ...). Built-ins are
    seeded but fully editable."""

    __tablename__ = "niche_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    label_bg: Mapped[str | None] = mapped_column(String(120))
    category_query: Mapped[str] = mapped_column(String(200))
    included_type: Mapped[str | None] = mapped_column(String(100))
    keywords: Mapped[str | None] = mapped_column(String(300))
    match_types: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list, server_default="{}")
    calling_window_start: Mapped[str | None] = mapped_column(String(5))
    calling_window_end: Mapped[str | None] = mapped_column(String(5))
    booking_oriented: Mapped[bool] = mapped_column(Boolean, default=False)
    discovery_dependent: Mapped[bool] = mapped_column(Boolean, default=True)
    strong_opportunities: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), default=list, server_default="{}"
    )
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=100)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    columns: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    rows: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="preview")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
