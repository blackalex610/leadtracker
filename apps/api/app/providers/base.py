"""Provider abstraction. Anything that can search local businesses implements
:class:`BusinessSearchProvider`; the rest of the app only sees
:class:`ProviderPlace` records."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class SearchParams:
    text_query: str
    region_code: str | None = "BG"
    language_code: str | None = "bg"
    min_rating: float | None = None
    included_type: str | None = None
    open_now: bool | None = None
    page_size: int = 20
    page_token: str | None = None

    def cache_identity(self) -> dict[str, Any]:
        """Parameters that define the result set (page token excluded)."""
        return {
            "q": self.text_query.strip().lower(),
            "region": self.region_code,
            "lang": self.language_code,
            "min_rating": self.min_rating,
            "type": self.included_type,
            "open_now": self.open_now,
            "page_size": self.page_size,
        }


@dataclass(slots=True)
class ProviderPlace:
    provider: str
    external_id: str
    name: str
    primary_type: str | None = None
    primary_type_label: str | None = None
    types: list[str] = field(default_factory=list)
    formatted_address: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    national_phone: str | None = None
    international_phone: str | None = None
    website_url: str | None = None
    maps_url: str | None = None
    rating: float | None = None
    review_count: int | None = None
    opening_hours: dict[str, Any] | None = None
    utc_offset_minutes: int | None = None
    business_status: str | None = None
    photo_count: int | None = None
    description: str | None = None
    description_requested: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    raw: dict[str, Any] = field(default_factory=dict)
    is_demo: bool = False

    def to_cache(self) -> dict[str, Any]:
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data["fetched_at"] = self.fetched_at.isoformat()
        return data

    @classmethod
    def from_cache(cls, data: dict[str, Any]) -> ProviderPlace:
        values = dict(data)
        values["fetched_at"] = datetime.fromisoformat(values["fetched_at"])
        return cls(**values)


@dataclass(slots=True)
class BusinessSearchResult:
    places: list[ProviderPlace]
    next_page_token: str | None
    sku: str


# ---------------------------------------------------------------------------
# Errors. ``code`` values are stable identifiers surfaced to the UI.
# ---------------------------------------------------------------------------


class ProviderError(Exception):
    code = "provider_error"
    retryable = False
    default_message = "The business data provider returned an error."

    def __init__(
        self, message: str | None = None, *, status_code: int | None = None, retry_after: float | None = None
    ):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.status_code = status_code
        self.retry_after = retry_after


class ProviderNotConfiguredError(ProviderError):
    code = "provider_not_configured"
    default_message = (
        "Provider not configured. Set PROVIDER_API_KEY (or enable DEMO_MODE for synthetic data)."
    )


class ProviderAuthError(ProviderError):
    code = "invalid_api_key"
    default_message = "The provider rejected the API key. Check PROVIDER_API_KEY."


class ProviderPermissionError(ProviderError):
    code = "permission_denied"
    default_message = "The API key is not allowed to call this API."


class ProviderQuotaError(ProviderError):
    code = "quota_exceeded"
    default_message = "Provider quota exceeded."


class ProviderRateLimitError(ProviderError):
    code = "rate_limited"
    retryable = True
    default_message = "Provider rate limit reached."


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"
    retryable = True
    default_message = "The provider is temporarily unavailable."


class ProviderTimeoutError(ProviderError):
    code = "timeout"
    retryable = True
    default_message = "The provider did not respond in time."


class ProviderNetworkError(ProviderError):
    code = "network_error"
    retryable = True
    default_message = "Could not reach the provider."


class ProviderBadRequestError(ProviderError):
    code = "bad_request"
    default_message = "The provider rejected the request."


class ProviderNotFoundError(ProviderError):
    code = "not_found"
    default_message = "Business not found at the provider."


@runtime_checkable
class BusinessSearchProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    @property
    def search_sku(self) -> str: ...

    @property
    def details_sku(self) -> str: ...

    async def search_businesses(self, params: SearchParams) -> BusinessSearchResult: ...

    async def get_business_details(
        self, external_id: str, *, language_code: str | None = None, region_code: str | None = None
    ) -> ProviderPlace: ...

    async def aclose(self) -> None: ...
