"""Google Places API (New) provider — https://places.googleapis.com/v1

Cost strategy: Text Search (New) can return Enterprise-tier fields (phone,
website, rating, review count, opening hours) directly, 20 places per billable
request. We therefore never call Place Details during a search; Details is
only used for an explicit single-lead refresh. Only the fields we actually use
are requested via ``X-Goog-FieldMask``.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any
from urllib.parse import quote

import httpx

from app.log import get_logger
from app.providers.base import (
    BusinessSearchResult,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderError,
    ProviderNetworkError,
    ProviderNotConfiguredError,
    ProviderNotFoundError,
    ProviderPermissionError,
    ProviderPlace,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SearchParams,
)
from app.providers.resilience import AsyncRateLimiter, SleepFn, with_retries

log = get_logger(__name__)

PROVIDER_NAME = "google_places"

# Fields (without the "places." prefix). Pro-tier fields are free riders once
# any Enterprise field is requested; Enterprise fields are the ones we need.
_BASE_FIELDS = [
    "id",
    "displayName",
    "formattedAddress",
    "addressComponents",
    "location",
    "types",
    "primaryType",
    "primaryTypeDisplayName",
    "googleMapsUri",
    "businessStatus",
    "utcOffsetMinutes",
    "photos",
    # Enterprise
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "websiteUri",
    "rating",
    "userRatingCount",
    "regularOpeningHours",
]
_ATMOSPHERE_FIELDS = ["editorialSummary"]

_SKUS = {
    "enterprise": ("text_search_enterprise", "place_details_enterprise"),
    "enterprise_atmosphere": ("text_search_enterprise_atmosphere", "place_details_enterprise_atmosphere"),
}


def field_list(tier: str) -> list[str]:
    return _BASE_FIELDS + (_ATMOSPHERE_FIELDS if tier == "enterprise_atmosphere" else [])


def search_field_mask(tier: str) -> str:
    return ",".join([f"places.{f}" for f in field_list(tier)] + ["nextPageToken"])


def details_field_mask(tier: str) -> str:
    return ",".join(field_list(tier))


def _provider_min_rating(min_rating: float | None) -> float | None:
    """The API rounds minRating *up* to a 0.5 step; round down instead so no
    qualifying place is dropped. The exact threshold is re-applied locally."""
    if min_rating is None or min_rating <= 0:
        return None
    return math.floor(min(min_rating, 5.0) * 2) / 2


def classify_error(status_code: int, payload: Any, retry_after: float | None = None) -> ProviderError:
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    message = str(error.get("message") or "")
    status_text = str(error.get("status") or "")
    reasons = {
        str(d.get("reason"))
        for d in error.get("details", []) or []
        if isinstance(d, dict) and d.get("reason")
    }
    lowered = message.lower()

    if "API_KEY_INVALID" in reasons or "api key not valid" in lowered or status_code == 401:
        return ProviderAuthError(status_code=status_code)
    if status_code == 403 or status_text == "PERMISSION_DENIED":
        if "SERVICE_DISABLED" in reasons or "has not been used" in lowered or "is disabled" in lowered:
            return ProviderPermissionError(
                "Places API (New) is not enabled for this Google Cloud project. Enable 'Places API (New)' "
                "in the Google Cloud console.",
                status_code=status_code,
            )
        if "BILLING_DISABLED" in reasons or "billing" in lowered:
            return ProviderPermissionError(
                "Billing is not enabled for the Google Cloud project that owns this API key.",
                status_code=status_code,
            )
        if any(r.startswith("API_KEY_") for r in reasons) or "blocked" in lowered:
            return ProviderPermissionError(
                "The API key's restrictions block this request (check API/IP restrictions on the key).",
                status_code=status_code,
            )
        return ProviderPermissionError(message or None, status_code=status_code)
    if status_code == 429 or status_text == "RESOURCE_EXHAUSTED":
        if "per day" in lowered or "daily" in lowered:
            return ProviderQuotaError(
                "Daily provider quota exhausted. Raise the quota in Google Cloud or try again tomorrow.",
                status_code=status_code,
            )
        return ProviderRateLimitError(status_code=status_code, retry_after=retry_after)
    if status_code == 404:
        return ProviderNotFoundError(status_code=status_code)
    if status_code >= 500:
        return ProviderUnavailableError(status_code=status_code, retry_after=retry_after)
    if status_code == 400:
        return ProviderBadRequestError(message or None, status_code=status_code)
    return ProviderError(message or f"Unexpected provider response ({status_code})", status_code=status_code)


def _component(components: list[dict[str, Any]], *types: str, short: bool = False) -> str | None:
    for wanted in types:
        for comp in components:
            if wanted in (comp.get("types") or []):
                value = comp.get("shortText" if short else "longText") or comp.get("longText")
                if value:
                    return str(value)
    return None


def parse_place(data: dict[str, Any], *, description_requested: bool = False) -> ProviderPlace:
    components = data.get("addressComponents") or []
    location = data.get("location") or {}
    hours = data.get("regularOpeningHours")
    raw = {k: v for k, v in data.items() if k != "photos"}
    photos = data.get("photos")
    return ProviderPlace(
        provider=PROVIDER_NAME,
        external_id=str(data["id"]),
        name=str((data.get("displayName") or {}).get("text") or "").strip() or "(unnamed)",
        primary_type=data.get("primaryType"),
        primary_type_label=(data.get("primaryTypeDisplayName") or {}).get("text"),
        types=list(data.get("types") or []),
        formatted_address=data.get("formattedAddress"),
        city=_component(
            components,
            "locality",
            "postal_town",
            "administrative_area_level_2",
            "administrative_area_level_1",
        ),
        neighborhood=_component(components, "neighborhood", "sublocality_level_1", "sublocality"),
        postal_code=_component(components, "postal_code"),
        country_code=_component(components, "country", short=True),
        latitude=location.get("latitude"),
        longitude=location.get("longitude"),
        national_phone=data.get("nationalPhoneNumber"),
        international_phone=data.get("internationalPhoneNumber"),
        website_url=data.get("websiteUri"),
        maps_url=data.get("googleMapsUri"),
        rating=data.get("rating"),
        review_count=data.get("userRatingCount"),
        opening_hours=(
            {
                "periods": hours.get("periods") or [],
                "weekday_descriptions": hours.get("weekdayDescriptions") or [],
            }
            if isinstance(hours, dict)
            else None
        ),
        utc_offset_minutes=data.get("utcOffsetMinutes"),
        business_status=data.get("businessStatus"),
        # The API returns at most 10 photo references; None means "not returned".
        photo_count=len(photos) if isinstance(photos, list) else (0 if "photos" not in data else None),
        description=(data.get("editorialSummary") or {}).get("text"),
        description_requested=description_requested,
        raw=raw,
    )


class GooglePlacesProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://places.googleapis.com/v1",
        timeout: float = 20.0,
        field_tier: str = "enterprise",
        requests_per_second: float = 5.0,
        max_attempts: int = 4,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._api_key = api_key
        self._field_tier = field_tier if field_tier in _SKUS else "enterprise"
        self._max_attempts = max_attempts
        self._sleep = sleep
        self.limiter = AsyncRateLimiter(requests_per_second, burst=2, sleep=sleep)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, connect=10.0),
            transport=transport,
            headers={"User-Agent": "leadtracker/1.0"},
        )

    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def search_sku(self) -> str:
        return _SKUS[self._field_tier][0]

    @property
    def details_sku(self) -> str:
        return _SKUS[self._field_tier][1]

    @property
    def description_requested(self) -> bool:
        return self._field_tier == "enterprise_atmosphere"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        field_mask: str,
        json: Any = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise ProviderNotConfiguredError()
        headers = {"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": field_mask}

        async def attempt() -> dict[str, Any]:
            await self.limiter.acquire()
            try:
                response = await self._client.request(method, path, json=json, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError() from exc
            except httpx.TransportError as exc:
                raise ProviderNetworkError(f"Could not reach the provider ({type(exc).__name__}).") from exc
            if response.status_code >= 400:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                retry_after = _retry_after(response)
                error = classify_error(response.status_code, payload, retry_after)
                log.warning(
                    "provider_error",
                    provider=self.name,
                    status=response.status_code,
                    code=error.code,
                    path=path.split("?")[0],
                )
                raise error
            try:
                data = response.json()
            except ValueError as exc:
                raise ProviderUnavailableError("Provider returned an invalid response.") from exc
            return data if isinstance(data, dict) else {}

        return await with_retries(attempt, attempts=self._max_attempts, sleep=self._sleep, op_name=path)

    async def search_businesses(self, params: SearchParams) -> BusinessSearchResult:
        body: dict[str, Any] = {"textQuery": params.text_query, "pageSize": max(1, min(params.page_size, 20))}
        if params.language_code:
            body["languageCode"] = params.language_code
        if params.region_code:
            body["regionCode"] = params.region_code
        provider_min = _provider_min_rating(params.min_rating)
        if provider_min is not None:
            body["minRating"] = provider_min
        if params.included_type:
            body["includedType"] = params.included_type
            body["strictTypeFiltering"] = False
        if params.open_now:
            body["openNow"] = True
        if params.page_token:
            body["pageToken"] = params.page_token

        data = await self._request(
            "POST", "/places:searchText", field_mask=search_field_mask(self._field_tier), json=body
        )
        places = [
            parse_place(p, description_requested=self.description_requested)
            for p in data.get("places") or []
            if isinstance(p, dict) and p.get("id")
        ]
        return BusinessSearchResult(
            places=places, next_page_token=data.get("nextPageToken"), sku=self.search_sku
        )

    async def get_business_details(
        self, external_id: str, *, language_code: str | None = None, region_code: str | None = None
    ) -> ProviderPlace:
        params: dict[str, str] = {}
        if language_code:
            params["languageCode"] = language_code
        if region_code:
            params["regionCode"] = region_code
        data = await self._request(
            "GET",
            f"/places/{quote(external_id, safe='')}",
            field_mask=details_field_mask(self._field_tier),
            params=params or None,
        )
        if not data.get("id"):
            raise ProviderNotFoundError()
        return parse_place(data, description_requested=self.description_requested)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
