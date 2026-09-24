"""CSV import with preview, header mapping, validation and duplicate detection.

Imports never blindly overwrite: duplicates are skipped by default, or merged
with ``fill_empty`` which only fills fields that are currently empty.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PhoneSource
from app.core.phone import normalize_phone
from app.core.text import address_key, dedupe_domain, fold, name_key, normalize_url
from app.models import Business, BusinessContact, Note
from app.services.businesses import BusinessRecord, upsert_business
from app.services.dedupe import NAME_MATCH_WITH_DOMAIN, NAME_MATCH_WITH_PHONE

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
PREVIEW_ROWS = 100

TARGET_FIELDS = [
    "name",
    "phone",
    "website",
    "address",
    "city",
    "category",
    "rating",
    "reviews",
    "google_maps_url",
    "notes",
]

SYNONYMS: dict[str, list[str]] = {
    "name": [
        "name",
        "business",
        "business name",
        "company",
        "company name",
        "title",
        "име",
        "фирма",
        "наименование",
        "бизнес",
        "обект",
        "организация",
    ],
    "phone": [
        "phone",
        "telephone",
        "tel",
        "phone number",
        "mobile",
        "gsm",
        "contact number",
        "телефон",
        "тел",
        "мобилен",
        "телефонен номер",
        "gsm номер",
    ],
    "website": [
        "website",
        "url",
        "site",
        "web",
        "web site",
        "homepage",
        "domain",
        "уебсайт",
        "сайт",
        "интернет страница",
        "домейн",
    ],
    "address": ["address", "street", "full address", "location", "адрес", "улица"],
    "city": ["city", "town", "locality", "град", "населено място"],
    "category": ["category", "type", "industry", "niche", "категория", "дейност", "тип"],
    "rating": ["rating", "stars", "рейтинг", "оценка"],
    "reviews": ["reviews", "review count", "reviews count", "number of reviews", "отзиви", "брой отзиви"],
    "google_maps_url": ["google maps", "google maps url", "maps url", "maps link", "maps", "карта"],
    "notes": ["notes", "note", "comment", "comments", "бележки", "бележка", "коментар"],
}

_MAPS_URL = re.compile(
    r"^https://(www\.)?(google\.[a-z.]+/maps|maps\.google\.[a-z.]+|maps\.app\.goo\.gl|goo\.gl/maps)", re.I
)


class ImportError_(ValueError):
    pass


def decode_csv(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ImportError_(f"File too large (max {MAX_BYTES // (1024 * 1024)} MB)")
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def parse_csv(text: str) -> tuple[list[str], list[list[str]]]:
    sample = text[:20_000]
    try:
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ImportError_("The file is empty")
    header = [h.strip() for h in rows[0]]
    body = rows[1 : MAX_ROWS + 1]
    if len(rows) - 1 > MAX_ROWS:
        raise ImportError_(f"Too many rows (max {MAX_ROWS})")
    return header, body


def _norm_header(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9а-я]+", " ", value.lower()).split())


def guess_mapping(columns: list[str]) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {field: None for field in TARGET_FIELDS}
    normalized = {col: _norm_header(col) for col in columns}
    folded = {col: fold(col) for col in columns}
    for field in TARGET_FIELDS:
        for col in columns:
            if col in mapping.values():
                continue
            if normalized[col] in SYNONYMS[field] or folded[col] in [fold(s) for s in SYNONYMS[field]]:
                mapping[field] = col
                break
    return mapping


def _num(value: str | None, as_int: bool = False) -> float | int | None:
    if not value:
        return None
    cleaned = value.strip().replace(" ", "").replace(",", ".")
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return int(number) if as_int else number


@dataclass(slots=True)
class ParsedRow:
    index: int
    values: dict[str, str | None]
    name_key: str
    phone_e164: str | None
    domain: str | None
    address_key: str | None
    issues: list[str]

    @property
    def valid(self) -> bool:
        return bool(self.values.get("name"))


def extract_rows(
    columns: list[str], rows: list[list[str]], mapping: dict[str, str | None], default_region: str
) -> list[ParsedRow]:
    index_of = {col: i for i, col in enumerate(columns)}
    out: list[ParsedRow] = []
    for i, row in enumerate(rows):
        values: dict[str, str | None] = {}
        for field in TARGET_FIELDS:
            col = mapping.get(field)
            if col is None or col not in index_of:
                values[field] = None
                continue
            idx = index_of[col]
            cell = row[idx].strip() if idx < len(row) else ""
            values[field] = cell[:1000] or None
        issues: list[str] = []
        phone = normalize_phone(values.get("phone"), default_region) if values.get("phone") else None
        if values.get("phone") and phone is None:
            issues.append("Phone number could not be validated")
        if values.get("website") and not normalize_url(values["website"]):
            issues.append("Website URL is invalid")
        if not values.get("name"):
            issues.append("Missing business name")
        out.append(
            ParsedRow(
                index=i,
                values=values,
                name_key=name_key(values.get("name")),
                phone_e164=phone.e164 if phone else None,
                domain=dedupe_domain(values.get("website")),
                address_key=address_key(values.get("address"), values.get("city")),
                issues=issues,
            )
        )
    return out


@dataclass(slots=True)
class DuplicateInfo:
    business_id: int | None
    business_name: str | None
    reason: str


async def detect_duplicates(session: AsyncSession, rows: list[ParsedRow]) -> dict[int, DuplicateInfo]:
    """Batch duplicate detection against the database and within the file."""
    phones = {r.phone_e164 for r in rows if r.phone_e164}
    domains = {r.domain for r in rows if r.domain}
    name_keys = {r.name_key for r in rows if r.name_key and r.address_key}
    conditions = []
    if phones:
        contact_ids = select(BusinessContact.business_id).where(BusinessContact.normalized_phone.in_(phones))
        conditions += [Business.normalized_phone.in_(phones), Business.id.in_(contact_ids)]
    if domains:
        conditions.append(Business.website_domain.in_(domains))
    if name_keys:
        conditions.append(Business.name_key.in_(name_keys))
    existing: list[Business] = []
    if conditions:
        existing = list(
            (await session.execute(select(Business).where(or_(*conditions)).limit(50_000))).scalars()
        )
    contact_rows: list[tuple[int, str]] = []
    if phones:
        contact_result = await session.execute(
            select(BusinessContact.business_id, BusinessContact.normalized_phone).where(
                BusinessContact.normalized_phone.in_(phones)
            )
        )
        contact_rows = [(int(r[0]), str(r[1])) for r in contact_result.all()]
    by_id = {b.id: b for b in existing}
    by_phone: dict[str, list[Business]] = {}
    for b in existing:
        if b.normalized_phone:
            by_phone.setdefault(b.normalized_phone, []).append(b)
    for bid, phone in contact_rows:
        if bid in by_id and by_id[bid] not in by_phone.get(phone, []):
            by_phone.setdefault(phone, []).append(by_id[bid])
    by_domain: dict[str, list[Business]] = {}
    for b in existing:
        if b.website_domain:
            by_domain.setdefault(b.website_domain, []).append(b)
    by_name_addr = {(b.name_key, b.address_key): b for b in existing if b.address_key}

    result: dict[int, DuplicateInfo] = {}
    seen_in_file: dict[str, int] = {}
    for row in rows:
        if not row.valid:
            continue
        match: DuplicateInfo | None = None
        if row.phone_e164:
            for b in by_phone.get(row.phone_e164, []):
                if fuzz.token_set_ratio(row.name_key, b.name_key) >= NAME_MATCH_WITH_PHONE or (
                    row.domain and row.domain == b.website_domain
                ):
                    match = DuplicateInfo(b.id, b.name, "phone")
                    break
        if match is None and row.domain:
            for b in by_domain.get(row.domain, []):
                if fuzz.token_set_ratio(row.name_key, b.name_key) >= NAME_MATCH_WITH_DOMAIN:
                    match = DuplicateInfo(b.id, b.name, "website_domain")
                    break
        if match is None and row.address_key and (row.name_key, row.address_key) in by_name_addr:
            b = by_name_addr[(row.name_key, row.address_key)]
            match = DuplicateInfo(b.id, b.name, "name_address")
        if match is None:
            keys = [
                k
                for k in (
                    row.phone_e164,
                    row.domain and f"d:{row.domain}",
                    row.address_key and f"n:{row.name_key}|{row.address_key}",
                )
                if k
            ]
            earlier = next((seen_in_file[k] for k in keys if k in seen_in_file), None)
            if earlier is not None:
                match = DuplicateInfo(None, f"row {earlier + 2}", "duplicate_in_file")
            for key in keys:
                seen_in_file.setdefault(key, row.index)
        if match is not None:
            result[row.index] = match
    return result


def record_from_row(row: ParsedRow) -> BusinessRecord:
    v = row.values
    maps_url = v.get("google_maps_url")
    rating = _num(v.get("rating"))
    reviews = _num(v.get("reviews"), as_int=True)
    return BusinessRecord(
        name=(v.get("name") or "").strip()[:300],
        provider="import",
        category=v.get("category"),
        address=v.get("address"),
        city=v.get("city"),
        phones=[phone for phone in [v.get("phone")] if phone],
        phone_source=PhoneSource.IMPORT.value,
        website_url=v.get("website") if v.get("website") and normalize_url(v.get("website")) else None,
        google_maps_url=maps_url if maps_url and _MAPS_URL.match(maps_url) else None,
        rating=float(rating) if rating is not None and 0 <= rating <= 5 else None,
        review_count=int(reviews) if reviews is not None and reviews >= 0 else None,
    )


async def commit_rows(
    session: AsyncSession,
    rows: list[ParsedRow],
    duplicates: dict[int, DuplicateInfo],
    *,
    strategy: str,
    skip_rows: set[int],
    default_region: str,
    user_id: int | None,
) -> tuple[dict[str, int], list[int]]:
    counts = {"created": 0, "merged": 0, "skipped_duplicates": 0, "invalid": 0}
    touched: list[int] = []
    for row in rows:
        if row.index in skip_rows:
            continue
        if not row.valid:
            counts["invalid"] += 1
            continue
        duplicate = duplicates.get(row.index)
        if duplicate is not None and strategy == "skip":
            counts["skipped_duplicates"] += 1
            continue
        outcome = await upsert_business(
            session, record_from_row(row), default_region=default_region, user_id=user_id, fill_only=True
        )
        counts["created" if outcome.created else "merged"] += 1
        if row.values.get("notes"):
            session.add(
                Note(business_id=outcome.business.id, user_id=user_id, body=f"[import] {row.values['notes']}")
            )
        touched.append(outcome.business.id)
    return counts, touched
