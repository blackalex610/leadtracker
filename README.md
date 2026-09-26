# Lead Tracker

**Prospecting software that finds local businesses in a chosen niche and area, audits their online presence, and tells a salesperson in a few seconds why each one is worth a call.**

A user picks a niche (gyms, salons, barbers, restaurants, dentists and so on) and a location. Lead Tracker pulls matching businesses from the Google Places API, normalizes and de-duplicates their phone numbers, audits each business's website and Google listing, and ranks the results by how much the business stands to gain from what the user is selling. Every lead comes with a written explanation of its score and a suggested pitch built only from what was actually observed.

```
niche + location → search (Google Places API) → save & de-duplicate → normalize phones
→ audit website → analyse Google profile → detect opportunities → score + priority
→ review → call (keyboard-driven) → export
```

It is not a scraper. Business data comes from the official Google Places API, the website auditor fetches only a handful of public pages per site and respects `robots.txt`, and every score is backed by a stored, human-readable reason.

Originally built for a sales team in Sofia, Bulgaria.

---

## Use cases

**Selling websites (primary use case).** Web design studios and freelancers need a steady list of businesses that need a new website. Lead Tracker surfaces businesses with no website at all, sites that are outdated or broken on mobile, sites without online booking or visible prices, and listings that link only to a Facebook page. Each lead arrives with the specific problems found, so the first call opens with something concrete instead of a generic pitch.

The same pipeline works for anyone who sells to local businesses:

| Who | What they filter for |
|---|---|
| SEO and digital marketing agencies | Weak Google profiles: missing hours, few photos, low review volume, category mismatches |
| Booking, POS and payment providers | Service businesses with no online booking or only phone reservations |
| B2B suppliers and service providers | Call lists segmented by niche, neighborhood, rating and opening hours |
| Market research and business development | Business density, ratings and digital maturity by niche and area |
| Franchise and expansion planning | Competitor coverage across neighborhoods before choosing a location |

The niche templates, scoring weights and pitch rules are all editable at runtime, so the tool can be pointed at a different offer without code changes.

---

## Engineering highlights

- **Explainable, deterministic scoring.** The opportunity engine is a configurable rule set, not a language model. Every lead has an Opportunity Score, tags such as `NO_WEBSITE` or `OUTDATED_WEBSITE`, a HOT / WARM / COLD priority and a stored reason for each.
- **Website auditing with 40+ signals** across technical, mobile, conversion, content and trust categories, in both English and Bulgarian.
- **SSRF-safe fetching.** The auditor resolves and pins IP addresses, blocks private ranges and ignores proxy variables, because it fetches URLs that come from third-party data.
- **Postgres as the job queue.** Background jobs are claimed with `SELECT … FOR UPDATE SKIP LOCKED`, so any number of workers can run without Redis. On serverless hosting the same jobs run in resumable 40-second slices.
- **Type-safe API contract.** TypeScript types are generated from the FastAPI OpenAPI schema, and CI fails if they drift.
- **Cost control built in.** Live cost estimates before a search runs, query caching and de-duplication, rate limiting, and per-SKU usage tracking against Google's price list.
- **Compliance by design.** A permanent do-not-contact list enforced at every stage, no personal data stored, and automatic expiry of Google data that the Maps Platform terms restrict.
- **Quality gates.** `mypy --strict`, Ruff, ESLint, pytest against a real PostgreSQL database, Vitest, Playwright end-to-end tests, Docker images and GitHub Actions CI.

**Stack:** Python, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL · React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui, TanStack Query · Docker, Vercel, Neon Postgres.

---

## Contents

1. [What it does](#1-what-it-does)
2. [Architecture](#2-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Environment variables](#4-environment-variables)
5. [Database setup](#5-database-setup)
6. [Development commands](#6-development-commands)
7. [Production deployment](#7-production-deployment)
8. [API provider setup](#8-api-provider-setup)
9. [Cost considerations](#9-cost-considerations)
10. [Website auditing limitations](#10-website-auditing-limitations)
11. [Data & privacy](#11-data--privacy)
12. [Troubleshooting](#12-troubleshooting)

Deeper docs: [`docs/architecture.md`](docs/architecture.md) ·
[`docs/scoring.md`](docs/scoring.md) · [`docs/deployment.md`](docs/deployment.md)

---

## 1. What it does

| Area | Highlights |
|---|---|
| **Find Leads** | Niche templates (Gyms, Beauty, Barbers, Restaurants, Dentists, …, all editable), city + optional neighborhood split (Sofia, Plovdiv, Varna, Burgas), keywords, min rating/reviews, has-website, open during calling hours, lead quality. Live cost estimate before you search. Runs as a background job with progress, cancel and retry. |
| **Phones** | libphonenumber normalization (`0888123456`, `+359 888 123 456`, `00359…` → `+359888123456`), type (mobile/landline), source, verification on answered calls, wrong-number flag, duplicate prevention. |
| **Website audit** | SSRF-safe fetcher; homepage + up to 3 relevant pages (contact, booking, services, prices, about). 40+ signals across technical, mobile, conversion, content and trust, in English **and Bulgarian** (e.g. „Запази час“, „Работно време“, prices only in лв after the 2026 euro switch). **Website Health** (0–100, higher is better) and a separate **Outdated index** (0–100, higher is more outdated). |
| **Google profile** | Missing phone/website/hours/address, review volume (as a visibility opportunity, not a verdict), few photos, category mismatch, closed status. |
| **Opportunity engine** | Deterministic, configurable rules → **Opportunity Score**, tags (`NO_WEBSITE`, `NO_BOOKING`, `OUTDATED_WEBSITE`, …) and **HOT / WARM / COLD** with a written reason. No LLM. |
| **Leads** | Dense server-side table (10k+ rows), URL-synced filters, quick filters, sorting, bulk actions, CSV export of the current view. |
| **Lead workspace** | "Why this lead?", EN/BG pitch built only from observed signals, audit breakdown, Google gaps, hours, call outcomes, notes, activity. |
| **Calling mode** | One lead at a time, `C` call · `N` no answer · `B` callback · `I` interested · `X` not interested · `D` do not contact (press twice) · `←/→`. Callbacks first, one lead per phone number, recently-called leads cooled down. |
| **Do not contact** | Permanent suppression list by phone number, enforced when discovering, queueing and displaying leads; only an explicit re-enable lifts it. |
| **Import / export** | CSV import with header mapping (EN/BG), UTF-8 or Windows-1251, preview, duplicate detection, "skip" or "fill empty fields only". UTF-8 (+BOM) export with formula-injection protection. |
| **Cost tracking** | Every provider request and cache hit recorded per SKU; monthly estimate from an editable price table (incl. free tiers). |

## 2. Architecture

```
apps/
  api/        FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 · httpx
    app/
      providers/   BusinessSearchProvider interface, Google Places (New), demo provider
      audit/       SafeFetcher (SSRF), robots, HTML model, analyzers, score calculator
      scoring/     opportunity engine, Google profile analysis, pitch, data quality
      services/    upsert/dedupe, search pipeline, calls, calling queue, CSV, settings, usage
      worker/      Postgres job queue (FOR UPDATE SKIP LOCKED) + runner
      api/routes/  REST endpoints (OpenAPI at /api/docs)
  web/        React 19 · Vite · TypeScript · Tailwind v4 · shadcn/ui (Radix) · TanStack Query · RHF + Zod
packages/
  shared/     TypeScript types generated from the API's OpenAPI schema + UI label constants
docker/       Dockerfiles, nginx config, compose helpers
docs/         architecture, scoring rules, deployment
```

* **One database, no Redis.** Background jobs live in Postgres and are claimed with
  `SELECT … FOR UPDATE SKIP LOCKED`; any number of workers can run. The worker runs
  inside the API process by default (`RUN_WORKER=true`) or separately
  (`python -m app.worker`).
* **Replaceable provider.** Everything above `app/providers` only sees
  `ProviderPlace` records; add a provider by implementing `BusinessSearchProvider`.
* **Type-safe contract.** `pnpm gen:api` regenerates `packages/shared` from the
  FastAPI schema; CI fails if it is stale.
* **Future AI.** `LeadInsightProvider` (Python and TS) is defined but unused — V1 is fully deterministic.

## 3. Prerequisites

* Python 3.11+ and [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
* Node.js 22+ and pnpm 10 (`corepack enable`)
* PostgreSQL 14+ (16 recommended) — local install or `docker compose up -d db`
* Optional: Docker for the full containerized stack
* For real searches: a Google Cloud project with **Places API (New)** enabled (see §8)

## 4. Environment variables

Copy the template and edit it:

```bash
cp .env.example .env
```

The API reads `.env` from the repo root (or `apps/api/.env`). Key variables — the
full, commented list is in [`.env.example`](.env.example):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://leadtracker:leadtracker@localhost:5432/leadtracker` | Async SQLAlchemy URL |
| `PROVIDER_API_KEY` | — | Google Places API (New) key. **Empty = "Provider not configured"** (no fake data). |
| `PLACES_FIELD_TIER` | `enterprise` | `enterprise` (phone/website/rating/hours) or `enterprise_atmosphere` (+ description, pricier) |
| `DEMO_MODE` | `false` | Synthetic businesses for UI testing, no API calls |
| `DEFAULT_COUNTRY` / `DEFAULT_CITY` / `TIMEZONE` | `BG` / `Sofia` / `Europe/Sofia` | Defaults for runtime settings |
| `WEBSITE_AUDIT_TIMEOUT` | `10000` | Per-request timeout (ms) |
| `MAX_CONCURRENT_AUDITS` | `5` | Parallel website audits |
| `PAGESPEED_API_KEY` | — | Optional Lighthouse data (PageSpeed Insights) |
| `RUN_WORKER` | `true` (`false` on serverless) | Run jobs inside the API process |
| `AUTH_MODE` | `none` | `none` or `token` (per-user access tokens) |
| `SECRET_KEY` | — | ≥32 random chars; required when `AUTH_MODE=token` |
| `ADMIN_TOKEN` / `ADMIN_EMAIL` | — / `admin@leadtracker.local` | Bootstrap admin who signs in with `ADMIN_TOKEN` (≥24 chars) — for hosts without a shell (Vercel) |
| `SERVERLESS` | auto (`true` on Vercel) | No resident worker: jobs run in resumable slices (`WORKER_RUN_BUDGET_SECONDS`, default 40) |
| `CRON_SECRET` | — | Protects the daily `/api/worker/cron` maintenance call (Vercel Cron) |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Only needed for cross-origin frontends |
| `VITE_API_BASE_URL` | empty | Frontend build: empty = same-origin `/api` |

Everything else (scoring weights, calling hours, audit limits, cache TTL, CSV
format, pricing) is edited at runtime in **Settings** and stored in the database.
Secrets are never stored in the database or the browser, and are redacted from logs.

## 5. Database setup

**Option A — Docker:**

```bash
docker compose up -d db          # Postgres 16 on :5432, creates leadtracker + leadtracker_test
```

**Option B — local PostgreSQL:**

```bash
sudo -u postgres psql -c "CREATE USER leadtracker WITH PASSWORD 'leadtracker' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE leadtracker OWNER leadtracker;"
sudo -u postgres psql -c "CREATE DATABASE leadtracker_test OWNER leadtracker;"
sudo -u postgres psql -c "CREATE DATABASE leadtracker_e2e OWNER leadtracker;"   # optional, for make e2e
```

Then apply migrations (creates all tables, indexes and the `pg_trgm` extension):

```bash
cd apps/api && uv sync && uv run alembic upgrade head
```

Built-in niche templates and a default user are seeded on first API start.

## 6. Development commands

```bash
make install        # uv sync + pnpm install
make db             # (optional) Postgres in Docker
make migrate        # alembic upgrade head
make api            # API + embedded worker on http://127.0.0.1:8000 (docs: /api/docs)
make web            # frontend on http://127.0.0.1:5173 (proxies /api → :8000)
```

**Try it without an API key** (clearly synthetic data, dialing disabled):

```bash
make seed-demo      # ~120 demo businesses across Sofia, Plovdiv, Varna
make demo           # API in DEMO_MODE; then `make web` in another terminal
```

Quality gates (the same as CI):

```bash
make lint           # ruff + eslint
make typecheck      # mypy --strict + tsc
make test           # pytest (real Postgres, *_test DB) + vitest
make e2e            # Playwright against the real stack in demo mode (db: leadtracker_e2e)
make build          # production frontend build
make gen-api        # regenerate packages/shared types after changing API schemas
```

Useful CLI commands (`cd apps/api`):

```bash
uv run python -m app.cli create-user --email ana@example.com --name "Ana" --admin   # prints an access token
uv run python -m app.cli rotate-token --email ana@example.com
uv run python -m app.cli rescore           # recompute every lead's score
uv run python -m app.cli purge-demo        # delete synthetic demo records
```

Backend tests need a database whose name ends in `_test` (the suite drops and
recreates its schema): `TEST_DATABASE_URL=postgresql+asyncpg://…/leadtracker_test`.

## 7. Production deployment

### Vercel (all-in-one, quickest)

One Vercel project serves the web app as static files and the whole FastAPI backend
as a Python function (`api/index.py`, config in [`vercel.json`](vercel.json)); the
database is Neon Postgres from the Vercel Marketplace.

1. **Import** the GitHub repository at <https://vercel.com/new>. Keep the **Root
   Directory at the repository root** (`./`) and the framework preset **Other** —
   `vercel.json` sets the build.
2. **Database:** Project → *Storage* → *Create* → **Neon** (Postgres), region
   **Frankfurt (eu-central-1)** (the function runs in `fra1`), connect it to all
   environments. It adds `DATABASE_URL` / `DATABASE_URL_UNPOOLED` automatically.
3. **Environment variables** (Project → Settings → Environment Variables):

   | Name | Value |
   |---|---|
   | `AUTH_MODE` | `token` |
   | `SECRET_KEY` | 40+ random characters (never typed again) |
   | `ADMIN_TOKEN` | the password you will sign in with (24+ characters) |
   | `ADMIN_EMAIL` | your e-mail (optional) |
   | `PROVIDER_API_KEY` | Google Places API (New) key |
   | `CRON_SECRET` | 32+ random characters (optional, enables the daily cron) |

4. **Deploy** (or *Redeploy* after changing variables). Open the URL and sign in with
   `ADMIN_TOKEN`. The first request creates the database schema.

How background work runs there: Vercel has no always-on process, so search jobs,
audits and rescoring run in resumable ~40-second slices. The open app triggers the
next slice (`POST /api/worker/run`) while a job is active, and a daily Vercel Cron
picks up anything left over. A job therefore advances while someone has the app open;
closing the tab pauses it and it resumes where it stopped. Configuration mistakes
(no database, `AUTH_MODE=none` on a public URL, a short `SECRET_KEY`, no admin) are
reported in the app instead of a crash. Vercel's Hobby plan is for non-commercial use;
a sales team should use Pro. More in [`docs/deployment.md`](docs/deployment.md#vercel-all-in-one).

### Containers

Recommended topology for larger teams: **API + worker as containers** (Render,
Fly.io, Railway, a VPS…), **managed PostgreSQL**, frontend on nginx or Vercel.

```bash
# Backend image (API and worker share it)
docker build -f docker/api.Dockerfile -t leadtracker-api .
# API:     docker run -e DATABASE_URL=… -e PROVIDER_API_KEY=… -e RUN_MIGRATIONS=true -e RUN_WORKER=false -p 8000:8000 leadtracker-api
# Worker:  docker run -e DATABASE_URL=… -e PROVIDER_API_KEY=… leadtracker-api python -m app.worker

# Frontend (static, nginx proxies /api to API_UPSTREAM)
docker build -f docker/web.Dockerfile -t leadtracker-web .
docker run -e API_UPSTREAM=http://api:8000 -p 8080:80 leadtracker-web
```

Full stack locally: `docker compose up --build` → http://localhost:8080.

To host only the frontend on Vercel in front of container APIs, see
[`docs/deployment.md`](docs/deployment.md#vercel-frontend-only).

Production checklist:

* `ENVIRONMENT=production`, `AUTH_MODE=token`, strong `SECRET_KEY`, `SESSION_COOKIE_SECURE=true`
* Create users: `python -m app.cli create-user …` (inside the API container)
* `RUN_MIGRATIONS=true` on exactly one service; `RUN_WORKER=false` on the API when a separate worker runs
* Restrict the Google API key to Places API (New) and your server's egress IP
* Behind a proxy, uvicorn trusts `X-Forwarded-*` from `FORWARDED_ALLOW_IPS` (image default `*`; set it to your proxy's IP if the container is reachable directly)

More in [`docs/deployment.md`](docs/deployment.md).

## 8. API provider setup

1. Google Cloud console → create/select a project → **enable billing**.
2. **APIs & Services → Library → "Places API (New)" → Enable.** (The legacy
   "Places API" is not used.)
3. **Credentials → Create API key** → *Restrict key* → API restrictions: Places API (New);
   Application restrictions: IP addresses of your API server.
4. Set `PROVIDER_API_KEY=…` for the API and worker, restart them.
5. Settings → Provider shows "Configured".

How it is called: `POST https://places.googleapis.com/v1/places:searchText` with an
`X-Goog-FieldMask` listing only the fields the app uses
(`places.id, displayName, formattedAddress, addressComponents, location, types,
primaryType, primaryTypeDisplayName, googleMapsUri, businessStatus,
utcOffsetMinutes, photos, nationalPhoneNumber, internationalPhoneNumber,
websiteUri, rating, userRatingCount, regularOpeningHours, nextPageToken`).
Place Details (`GET /v1/places/{id}`) is only used for an explicit single-lead
"Refresh from Google". Errors are classified (invalid key, API not enabled,
billing disabled, key restrictions, quota, rate limit, unavailable) and shown
verbatim in the UI; retryable ones back off exponentially.

## 9. Cost considerations

* **One request = up to 20 businesses** with phone, website, rating and hours
  (Text Search Enterprise SKU). No per-business Details calls during searches.
* Text Search returns at most **60 results per query** (3 pages). To cover a city
  thoroughly, split by neighborhood — the form shows the maximum number of billable
  requests and the estimated cost *before* you run it.
* **Caching & de-duplication:** identical searches within `cache_ttl_hours`
  (Settings → Search) cost nothing; businesses are stored once no matter how many
  searches find them; concurrent identical queries share one request.
* **Limits:** `max_results_limit` caps a single search; the provider rate limiter
  (`provider_requests_per_second`) prevents bursts.
* **Tracking:** Dashboard → *This month* and Settings → *Pricing & usage* show
  requests per SKU, cache hits and the estimate after free tiers. Default prices
  live in one file (`apps/api/app/data/pricing.py`) and are editable at runtime —
  check them against Google's current price list; they change.
* `enterprise_atmosphere` (descriptions) and PageSpeed are opt-in because they cost
  more money or time.

## 10. Website auditing limitations

* Heuristic, markup-based analysis of the homepage plus up to 3 linked pages — not a
  Lighthouse audit. Mobile checks catch *obvious* problems (no/fixed viewport, Flash,
  fixed-width tables). Enable PageSpeed Insights for measured mobile performance.
* JavaScript-rendered sites (pure SPAs) may look emptier than they are; the audit
  does not execute scripts.
* Sites that block bots (401/403/429, Cloudflare challenges) or disallow crawling in
  robots.txt are reported as **skipped**, never as broken.
* Booking detection recognizes common platforms (Fresha, Booksy, Treatwell, Calendly,
  SimplyBook, OpenTable, …) and booking wording in EN/BG; custom booking forms with
  unusual wording may be missed.
* Response time is measured from the server running the audit, not a visitor's phone.
* Listings that link to Facebook/Instagram or a booking-platform profile are treated
  as "no own website" and are not audited.

## 11. Data & privacy

* Only business information relevant to prospecting is stored: business name,
  category, business phone(s), address, website, rating/review counts, opening hours.
  E-mail addresses found on websites are **not** stored; no personal data is scraped.
* **Do-not-contact is permanent.** Suppressed numbers are excluded from calling
  sessions for every business using them until explicitly re-enabled (the history is
  kept).
* **Google Maps Platform terms** restrict storing Places content: place IDs may be
  kept indefinitely and lat/lng for 30 days (enforced automatically by
  `GOOGLE_LATLNG_RETENTION_DAYS`). Review Google's terms for your use; the app records
  `source_timestamp` for every lead and offers a per-lead "Refresh from Google".
  Your own call outcomes, notes and website audits are your data. Google attribution
  is shown on provider data.
* Secrets only in environment variables; API keys and tokens are redacted from logs.
* Demo records are clearly labeled, use Ofcom's reserved fictional phone ranges and
  the reserved `.invalid` domain, cannot be dialed, and `purge-demo` removes them.

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| "Provider not configured" | Set `PROVIDER_API_KEY` (or `DEMO_MODE=true`) and restart API **and** worker. |
| `permission_denied: Places API (New) is not enabled` | Enable *Places API (New)* (not the legacy one) in the key's project. |
| `invalid_api_key` | Wrong key, or key restricted to other APIs. |
| `quota_exceeded` / `rate_limited` | Raise quotas in Google Cloud or lower `provider_requests_per_second`. |
| Jobs stay "Waiting for a worker" | `RUN_WORKER=true` on the API, or run `python -m app.worker`. Stuck jobs are re-queued after 3 minutes. On Vercel, keep the app open while a job runs (it drives the job). |
| Vercel: "setup_required" message | The message names the missing setting (database, `AUTH_MODE`, `SECRET_KEY`, `ADMIN_TOKEN`); fix it and redeploy. |
| Vercel: `maxDuration` error on deploy | Enable Fluid compute (Project → Settings → Functions), or lower `maxDuration` in `vercel.json` to your plan's limit. |
| Audits all fail with `dns_failure`/`connection_failed` | The API host needs outbound HTTP(S). Audits deliberately ignore `HTTP(S)_PROXY` (IP pinning for SSRF safety). |
| Cyrillic garbled in Excel | Keep "Include UTF-8 BOM" on; use `;` as delimiter for Bulgarian Excel (Settings → CSV). |
| `SECRET_KEY must be … 32 characters` | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| Tests refuse to run | `TEST_DATABASE_URL` must point to a database ending in `_test`. |
| Frontend can't reach API | Start the API on :8000 (Vite proxies `/api`), or set `VITE_DEV_API_TARGET`. |
| `CREATE EXTENSION pg_trgm` denied | Managed Postgres: enable the `pg_trgm` extension for the database owner. |

---

API documentation: `http://127.0.0.1:8000/api/docs` (Swagger) and `/api/redoc`.
