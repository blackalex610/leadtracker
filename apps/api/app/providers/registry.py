"""Provider selection. DEMO_MODE wins; otherwise the configured real provider.
Never falls back to demo data silently."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.providers.base import BusinessSearchProvider, ProviderNotConfiguredError
from app.providers.demo import DemoProvider
from app.providers.google_places import GooglePlacesProvider

_provider: BusinessSearchProvider | None = None


def provider_status(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or get_settings()
    if settings.demo_mode:
        return {"name": "demo", "configured": True, "demo_mode": True, "field_tier": None}
    return {
        "name": settings.provider,
        "configured": settings.provider_configured,
        "demo_mode": False,
        "field_tier": settings.places_field_tier,
    }


def get_provider(requests_per_second: float | None = None) -> BusinessSearchProvider:
    global _provider
    settings = get_settings()
    if _provider is None:
        if settings.demo_mode:
            _provider = DemoProvider()
        else:
            if not settings.provider_configured or settings.provider_api_key is None:
                raise ProviderNotConfiguredError()
            _provider = GooglePlacesProvider(
                settings.provider_api_key.get_secret_value(),
                base_url=settings.provider_base_url,
                timeout=settings.provider_timeout_seconds,
                field_tier=settings.places_field_tier,
            )
    if requests_per_second and isinstance(_provider, GooglePlacesProvider):
        _provider.limiter.set_rate(requests_per_second)
    return _provider


def set_provider(provider: BusinessSearchProvider | None) -> None:
    """Override the provider (tests)."""
    global _provider
    _provider = provider


async def close_provider() -> None:
    global _provider
    if _provider is not None:
        await _provider.aclose()
    _provider = None
