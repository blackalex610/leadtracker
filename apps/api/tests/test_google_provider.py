"""Google Places API (New) provider: request shape, parsing, errors, retries."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.providers.base import (
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderNotConfiguredError,
    ProviderNotFoundError,
    ProviderPermissionError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    SearchParams,
)
from app.providers.google_places import GooglePlacesProvider, classify_error, parse_place, search_field_mask
from app.providers.resilience import AsyncRateLimiter, with_retries

PLACE = {
    "id": "ChIJ123",
    "displayName": {"text": "Iron Gym Lozenets", "languageCode": "bg"},
    "formattedAddress": "ul. Krum Popov 5, 1164 Sofia, Bulgaria",
    "addressComponents": [
        {"longText": "5", "shortText": "5", "types": ["street_number"]},
        {
            "longText": "Lozenets",
            "shortText": "Lozenets",
            "types": ["sublocality_level_1", "sublocality", "political"],
        },
        {"longText": "Sofia", "shortText": "Sofia", "types": ["locality", "political"]},
        {"longText": "Bulgaria", "shortText": "BG", "types": ["country", "political"]},
        {"longText": "1164", "shortText": "1164", "types": ["postal_code"]},
    ],
    "location": {"latitude": 42.68, "longitude": 23.32},
    "types": ["gym", "health", "point_of_interest", "establishment"],
    "primaryType": "gym",
    "primaryTypeDisplayName": {"text": "Gym"},
    "googleMapsUri": "https://maps.google.com/?cid=123",
    "businessStatus": "OPERATIONAL",
    "nationalPhoneNumber": "088 812 3456",
    "internationalPhoneNumber": "+359 88 812 3456",
    "websiteUri": "http://irongym.bg/",
    "rating": 4.7,
    "userRatingCount": 312,
    "regularOpeningHours": {
        "openNow": True,
        "periods": [
            {"open": {"day": 1, "hour": 7, "minute": 0}, "close": {"day": 1, "hour": 22, "minute": 0}}
        ],
        "weekdayDescriptions": ["Monday: 7:00 AM – 10:00 PM"],
    },
    "utcOffsetMinutes": 180,
    "photos": [{"name": f"places/ChIJ123/photos/{i}"} for i in range(4)],
}


async def no_sleep(_: float) -> None:
    return None


def provider(handler: Any, **kwargs: Any) -> GooglePlacesProvider:
    return GooglePlacesProvider(
        "test-key-123456",
        transport=httpx.MockTransport(handler),
        sleep=no_sleep,
        requests_per_second=1000,
        **kwargs,
    )


async def test_text_search_request_uses_field_mask_and_new_api() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"places": [PLACE], "nextPageToken": "tok2"})

    p = provider(handler)
    result = await p.search_businesses(
        SearchParams(
            text_query="gyms in Sofia",
            region_code="BG",
            language_code="bg",
            min_rating=4.2,
            included_type="gym",
        )
    )
    request = captured[0]
    assert request.method == "POST"
    assert str(request.url) == "https://places.googleapis.com/v1/places:searchText"
    assert request.headers["X-Goog-Api-Key"] == "test-key-123456"
    mask = request.headers["X-Goog-FieldMask"]
    assert mask == search_field_mask("enterprise")
    for field in (
        "places.id",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.userRatingCount",
        "places.regularOpeningHours",
        "nextPageToken",
    ):
        assert field in mask.split(",")
    assert (
        "places.reviews" not in mask and "places.editorialSummary" not in mask
    )  # not paying for unused fields
    body = json.loads(request.content)
    assert body == {
        "textQuery": "gyms in Sofia",
        "pageSize": 20,
        "languageCode": "bg",
        "regionCode": "BG",
        "minRating": 4.0,
        "includedType": "gym",
        "strictTypeFiltering": False,
    }
    assert result.next_page_token == "tok2"
    assert result.sku == "text_search_enterprise"
    await p.aclose()


async def test_atmosphere_tier_adds_description_field_and_sku() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "places.editorialSummary" in request.headers["X-Goog-FieldMask"]
        return httpx.Response(200, json={"places": [{**PLACE, "editorialSummary": {"text": "Big gym"}}]})

    p = provider(handler, field_tier="enterprise_atmosphere")
    result = await p.search_businesses(SearchParams(text_query="gyms in Sofia", page_token="abc"))
    assert result.sku == "text_search_enterprise_atmosphere"
    assert result.places[0].description == "Big gym"
    assert result.places[0].description_requested


def test_parse_place_maps_all_fields() -> None:
    place = parse_place(PLACE)
    assert place.external_id == "ChIJ123"
    assert place.name == "Iron Gym Lozenets"
    assert place.city == "Sofia"
    assert place.neighborhood == "Lozenets"
    assert place.country_code == "BG"
    assert place.postal_code == "1164"
    assert place.international_phone == "+359 88 812 3456"
    assert place.website_url == "http://irongym.bg/"
    assert place.maps_url == "https://maps.google.com/?cid=123"
    assert place.rating == 4.7 and place.review_count == 312
    assert place.opening_hours and place.opening_hours["periods"][0]["open"]["day"] == 1
    assert place.photo_count == 4
    assert "photos" not in place.raw


def test_missing_optional_fields_become_none() -> None:
    place = parse_place({"id": "x", "displayName": {"text": "Bare"}})
    assert place.international_phone is None and place.website_url is None and place.rating is None
    assert place.opening_hours is None
    assert place.photo_count == 0


async def test_place_details_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/places/ChIJ123"
        assert request.url.params["languageCode"] == "bg"
        assert request.headers["X-Goog-FieldMask"].startswith("id,displayName")
        return httpx.Response(200, json=PLACE)

    place = await provider(handler).get_business_details("ChIJ123", language_code="bg")
    assert place.name == "Iron Gym Lozenets"


async def test_not_configured() -> None:
    p = GooglePlacesProvider(None, transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(ProviderNotConfiguredError):
        await p.search_businesses(SearchParams(text_query="gyms"))


def _err(status: int, status_text: str, message: str, reason: str | None = None) -> dict[str, Any]:
    details = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}] if reason else []
    return {"error": {"code": status, "status": status_text, "message": message, "details": details}}


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (
            400,
            _err(
                400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.", "API_KEY_INVALID"
            ),
            ProviderAuthError,
        ),
        (
            403,
            _err(
                403,
                "PERMISSION_DENIED",
                "Places API (New) has not been used in project 1",
                "SERVICE_DISABLED",
            ),
            ProviderPermissionError,
        ),
        (
            403,
            _err(
                403, "PERMISSION_DENIED", "Requests from this IP are blocked.", "API_KEY_IP_ADDRESS_BLOCKED"
            ),
            ProviderPermissionError,
        ),
        (
            429,
            _err(429, "RESOURCE_EXHAUSTED", "Quota exceeded for quota metric 'SearchText requests per day'"),
            ProviderQuotaError,
        ),
        (
            429,
            _err(429, "RESOURCE_EXHAUSTED", "Rate limit exceeded", "RATE_LIMIT_EXCEEDED"),
            ProviderRateLimitError,
        ),
        (404, _err(404, "NOT_FOUND", "Place not found"), ProviderNotFoundError),
        (500, _err(500, "INTERNAL", "Internal error"), ProviderUnavailableError),
        (400, _err(400, "INVALID_ARGUMENT", "Invalid pageSize"), ProviderBadRequestError),
    ],
)
def test_error_classification(status: int, payload: dict[str, Any], expected: type[Exception]) -> None:
    assert isinstance(classify_error(status, payload), expected)


async def test_retryable_errors_are_retried_then_succeed() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, json=_err(503, "UNAVAILABLE", "try later"))
        return httpx.Response(200, json={"places": [PLACE]})

    result = await provider(handler).search_businesses(SearchParams(text_query="gyms"))
    assert attempts["n"] == 3
    assert len(result.places) == 1


async def test_non_retryable_errors_fail_fast() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(400, json=_err(400, "INVALID_ARGUMENT", "API key not valid", "API_KEY_INVALID"))

    with pytest.raises(ProviderAuthError):
        await provider(handler).search_businesses(SearchParams(text_query="gyms"))
    assert attempts["n"] == 1


async def test_rate_limit_retries_are_bounded() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(
            429,
            json=_err(429, "RESOURCE_EXHAUSTED", "Rate limit", "RATE_LIMIT_EXCEEDED"),
            headers={"retry-after": "2"},
        )

    with pytest.raises(ProviderRateLimitError):
        await provider(handler, max_attempts=3).search_businesses(SearchParams(text_query="gyms"))
    assert attempts["n"] == 3


async def test_network_errors_are_classified_and_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    from app.providers.base import ProviderNetworkError

    with pytest.raises(ProviderNetworkError):
        await provider(handler, max_attempts=2).search_businesses(SearchParams(text_query="gyms"))


async def test_backoff_delays_grow_exponentially() -> None:
    delays: list[float] = []

    async def record(delay: float) -> None:
        delays.append(delay)

    async def always_fail() -> None:
        raise ProviderUnavailableError()

    with pytest.raises(ProviderUnavailableError):
        await with_retries(always_fail, attempts=4, base_delay=1.0, sleep=record)
    assert len(delays) == 3
    assert 0.8 <= delays[0] <= 1.2 and 1.6 <= delays[1] <= 2.4 and 3.2 <= delays[2] <= 4.8


async def test_rate_limiter_spaces_requests() -> None:
    clock = {"t": 0.0}
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    limiter = AsyncRateLimiter(2.0, burst=1, clock=lambda: clock["t"], sleep=fake_sleep)
    for _ in range(3):
        await limiter.acquire()
    assert sum(sleeps) == pytest.approx(1.0)
