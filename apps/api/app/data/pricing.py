"""Default provider pricing — the ONLY place list prices appear in the codebase.

Values are per 1,000 billable requests and the monthly free allowance per SKU
for Google Places API (New). They are editable at runtime in Settings → Pricing
and should be checked against https://mapsplatform.google.com/pricing/ as
Google changes them periodically.
"""

from __future__ import annotations

DEFAULT_PRICING_CURRENCY = "USD"

DEFAULT_SKU_PRICES: dict[str, dict[str, float]] = {
    "text_search_pro": {"price_per_1000": 32.0, "free_per_month": 5000},
    "text_search_enterprise": {"price_per_1000": 35.0, "free_per_month": 1000},
    "text_search_enterprise_atmosphere": {"price_per_1000": 40.0, "free_per_month": 1000},
    "place_details_enterprise": {"price_per_1000": 20.0, "free_per_month": 1000},
    "place_details_enterprise_atmosphere": {"price_per_1000": 25.0, "free_per_month": 1000},
    "pagespeed": {"price_per_1000": 0.0, "free_per_month": 0},
}
