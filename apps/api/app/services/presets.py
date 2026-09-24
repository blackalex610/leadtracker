from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.presets import BUILTIN_PRESETS
from app.models import AppSetting, Business, NichePreset
from app.scoring.inputs import NicheInfo

_SEED_KEY = "seed_state"


async def seed_builtin_presets(session: AsyncSession) -> int:
    """Seed built-in niche templates exactly once. Deleted built-ins stay deleted."""
    state = await session.get(AppSetting, _SEED_KEY)
    if state is not None and state.value.get("presets_seeded"):
        return 0
    existing = set((await session.execute(select(NichePreset.key))).scalars())
    added = 0
    for order, preset in enumerate(BUILTIN_PRESETS):
        if preset["key"] in existing:
            continue
        session.add(NichePreset(**preset, is_builtin=True, sort_order=order * 10))
        added += 1
    if state is None:
        session.add(AppSetting(key=_SEED_KEY, value={"presets_seeded": True}))
    else:
        state.value = {**state.value, "presets_seeded": True}
    await session.commit()
    return added


def to_niche(preset: NichePreset) -> NicheInfo:
    return NicheInfo(
        key=preset.key,
        label=preset.label,
        label_bg=preset.label_bg,
        booking_oriented=preset.booking_oriented,
        discovery_dependent=preset.discovery_dependent,
        match_types=list(preset.match_types or []),
    )


async def load_niches(session: AsyncSession) -> list[NicheInfo]:
    presets = (
        await session.execute(select(NichePreset).order_by(NichePreset.sort_order, NichePreset.id))
    ).scalars()
    return [to_niche(p) for p in presets]


def resolve_niche(business: Business, niches: list[NicheInfo]) -> NicheInfo | None:
    if business.niche_key:
        for niche in niches:
            if niche.key == business.niche_key:
                return niche
    if business.primary_type:
        for niche in niches:
            if business.primary_type in niche.match_types:
                return niche
    return None


async def preset_usage(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(
        select(Business.niche_key, func.count())
        .where(Business.niche_key.is_not(None))
        .group_by(Business.niche_key)
    )
    return {str(k): int(v) for k, v in rows.all()}
