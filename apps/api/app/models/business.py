"""Businesses (one row per real-world prospect) and their provider/contact records.

Lead workflow state (status, priority, score) is kept on the business row so the
main list can be filtered and sorted with a single indexed query at 10k+ rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DataQuality, LeadStatus, Priority, WebsiteStatus
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.audit import WebsiteAudit


class Business(TimestampMixin, Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- identity -------------------------------------------------------------
    name: Mapped[str] = mapped_column(String(300))
    name_key: Mapped[str] = mapped_column(String(300), index=True)
    category: Mapped[str | None] = mapped_column(String(200), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(200))
    primary_type: Mapped[str | None] = mapped_column(String(100))
    types: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list, server_default="{}")
    niche_key: Mapped[str | None] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    # --- location -------------------------------------------------------------
    address: Mapped[str | None] = mapped_column(String(500))
    address_key: Mapped[str | None] = mapped_column(String(500), index=True)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country_code: Mapped[str | None] = mapped_column(String(2))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    latlng_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    google_maps_url: Mapped[str | None] = mapped_column(String(500))

    # --- website --------------------------------------------------------------
    website_url: Mapped[str | None] = mapped_column(String(1000))
    website_domain: Mapped[str | None] = mapped_column(String(255), index=True)
    # own | social | booking_platform | link_hub (see app.core.text.website_kind)
    website_kind: Mapped[str | None] = mapped_column(String(20))
    website_status: Mapped[str] = mapped_column(String(20), default=WebsiteStatus.NONE.value)
    website_health_score: Mapped[int | None] = mapped_column(SmallInteger)
    outdated_score: Mapped[int | None] = mapped_column(SmallInteger)
    last_audit_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_audits.id", ondelete="SET NULL", use_alter=True)
    )
    last_audited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- primary phone (all numbers live in business_contacts) -------------------
    phone_raw: Mapped[str | None] = mapped_column(String(64))
    normalized_phone: Mapped[str | None] = mapped_column(String(20), index=True)
    national_phone: Mapped[str | None] = mapped_column(String(32))
    international_phone: Mapped[str | None] = mapped_column(String(32))
    phone_country_code: Mapped[int | None] = mapped_column(SmallInteger)
    phone_type: Mapped[str | None] = mapped_column(String(32))
    phone_source: Mapped[str | None] = mapped_column(String(32))
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    phone_invalid: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # --- Google Business Profile style data ------------------------------------
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    opening_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    utc_offset_minutes: Mapped[int | None] = mapped_column(Integer)
    business_status: Mapped[str | None] = mapped_column(String(40))
    photo_count: Mapped[int | None] = mapped_column(SmallInteger)
    google_profile_score: Mapped[int | None] = mapped_column(SmallInteger)
    google_signals: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")

    # --- provenance -------------------------------------------------------------
    provider: Mapped[str] = mapped_column(String(40))
    provider_place_id: Mapped[str | None] = mapped_column(String(255), index=True)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_quality: Mapped[str] = mapped_column(String(10), default=DataQuality.POOR.value)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # --- opportunity scoring -------------------------------------------------------
    opportunity_score: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0", index=True)
    priority: Mapped[str] = mapped_column(String(10), default=Priority.COLD.value, server_default="COLD")
    priority_rank: Mapped[int] = mapped_column(SmallInteger, default=2, server_default="2")
    priority_reason: Mapped[str | None] = mapped_column(Text)
    opportunity_types: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, server_default="{}")
    score_reasons: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    booking_oriented: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    strong_category: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    open_in_calling_window: Mapped[bool | None] = mapped_column(Boolean)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- lead workflow ------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20), default=LeadStatus.NEW.value, server_default="NEW", index=True
    )
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_contacted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    call_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    sources: Mapped[list[BusinessSource]] = relationship(
        back_populates="business", cascade="all, delete-orphan", lazy="raise"
    )
    contacts: Mapped[list[BusinessContact]] = relationship(
        back_populates="business", cascade="all, delete-orphan", lazy="raise"
    )
    last_audit: Mapped[WebsiteAudit | None] = relationship(foreign_keys=[last_audit_id], lazy="raise")

    __table_args__ = (
        Index("ix_businesses_list_default", "priority_rank", "opportunity_score"),
        Index("ix_businesses_opportunity_types", "opportunity_types", postgresql_using="gin"),
        Index(
            "ix_businesses_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class BusinessSource(Base):
    """A provider record (e.g. a Google place) linked to a business.

    ``(provider, external_id)`` is unique, which is what guarantees that a place
    appearing in 15 different searches is stored exactly once.
    """

    __tablename__ = "business_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(255))
    match_reason: Mapped[str | None] = mapped_column(String(40))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    business: Mapped[Business] = relationship(back_populates="sources", lazy="raise")

    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_business_sources_provider_external"),
    )


class BusinessContact(Base):
    __tablename__ = "business_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="phone")
    raw_phone: Mapped[str] = mapped_column(String(64))
    normalized_phone: Mapped[str] = mapped_column(String(20), index=True)
    national_format: Mapped[str | None] = mapped_column(String(32))
    international_format: Mapped[str | None] = mapped_column(String(32))
    country_code: Mapped[int | None] = mapped_column(SmallInteger)
    phone_type: Mapped[str | None] = mapped_column(String(32))
    phone_source: Mapped[str] = mapped_column(String(32))
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_method: Mapped[str | None] = mapped_column(String(40))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    invalid: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    business: Mapped[Business] = relationship(back_populates="contacts", lazy="raise")

    __table_args__ = (
        UniqueConstraint("business_id", "normalized_phone", name="uq_business_contacts_business_phone"),
    )
