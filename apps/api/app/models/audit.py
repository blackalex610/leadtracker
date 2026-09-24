from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WebsiteAudit(Base):
    """One audit run of a business website. Signals are stored individually so
    every score can be explained."""

    __tablename__ = "website_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(String(1000))
    final_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    https: Mapped[bool | None] = mapped_column(Boolean)
    redirect_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    redirect_chain: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    health_score: Mapped[int | None] = mapped_column(SmallInteger)
    outdated_score: Mapped[int | None] = mapped_column(SmallInteger)
    outdated_band: Mapped[str | None] = mapped_column(String(40))
    category_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    signals: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    outdated_signals: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    pages: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    analyzer_version: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
