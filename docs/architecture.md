# Architecture

## Request and job flow

```
Browser (React) ──/api──► FastAPI routes ──► services ──► PostgreSQL
                                   │
                                   └─ enqueue ─► jobs table ◄─ claim (FOR UPDATE SKIP LOCKED) ─ Worker(s)
                                                                     │
                     ┌───────────────────────────────────────────────┤
                     ▼                                               ▼
        ProviderGateway (cache, usage, locks)             WebsiteAuditor (SafeFetcher)
                     │                                               │
          GooglePlacesProvider / DemoProvider               public websites only
```

A search job:

1. `POST /api/search` validates `SearchRequest`, writes a `jobs` row (`queued`) and returns 202.
2. A worker claims it, plans queries (`"<category> <keywords> in <neighborhood>, <city>"`),
   and iterates result pages through `ProviderGateway.iter_search`:
   * per-key `asyncio.Lock` → concurrent identical searches share one fetch;
   * `provider_cache` (whole result sets, TTL) → repeat searches are free;
   * every request / cache hit → `api_usage` row with its SKU.
3. Each place is upserted (`services/businesses.upsert_business`): de-duplication, phone
   normalization into `business_contacts`, suppression check, source link in
   `business_sources`, then an initial score.
4. Businesses with an own website that is not freshly audited are audited concurrently
   (`audit.max_concurrent`), outside any DB transaction; each result is persisted and the
   lead re-scored.
5. Progress (`progress_processed/total`, `stage`, counters) is flushed after every page and
   every audit; the UI polls `GET /api/search-jobs/{id}`. Cancellation is a flag checked
   between pages/audits. Outcome: `completed`, `partial` (some queries failed),
   `failed` (nothing usable, error code shown), `cancelled`.

Workers heartbeat every 15 s; a job whose heartbeat is older than 3 minutes is re-queued
(or failed after `max_attempts`). A maintenance loop (advisory-locked) purges expired cache,
clears old lat/lng and stale import batches.

## De-duplication (`services/dedupe.py`)

In order:

1. `(provider, external_id)` in `business_sources` (unique constraint — the same place in 15
   searches is stored once);
2. same normalized phone **and** similar name (token-set ratio ≥ 85) or same own domain —
   one lead per callable number;
3. same own-website domain **and** very similar name (≥ 90) **and** compatible address;
4. identical normalized name + address keys (Cyrillic transliterated, legal forms and
   street words stripped).

Shared platforms (facebook.com, booksy.com, linktr.ee, …) are never a domain signal.
Provider refreshes overwrite provider-owned fields; imports only fill empty fields.
An `IntegrityError` race on insert is retried as an update.

## Website auditor (`app/audit`)

| Module | Role |
|---|---|
| `url_safety.py` | scheme/port/credential checks, internal hostnames, DNS resolution; **every** resolved IP must be globally routable (loopback, RFC1918, link-local incl. 169.254.169.254, CGNAT, ULA, multicast, reserved, IPv4-mapped/6to4/Teredo) |
| `fetcher.py` | connects to the validated IP (Host header + TLS SNI = hostname, so certificates are still verified), manual redirects re-validated per hop (max 5), streaming size cap, timeouts, charset sniffing (incl. windows-1251), ignores env proxies |
| `robots.py` | RFC 9309 semantics |
| `html.py` | selectolax/lexbor parse into `ParsedPage` (no scripts executed) |
| `analyzers/*` | technical, mobile, conversion, content, trust, outdated — pure functions of `AuditContext` |
| `signals.py` | the signal catalog: category, severity, label, penalty |
| `score.py` | Website Health + Outdated index |
| `service.py` | orchestration and failure classification (broken vs skipped) |
| `demo_sites.py` | fixtures for `*.demo.invalid` in demo mode |
| `pagespeed.py` | optional PageSpeed Insights |

## Data model (main tables)

| Table | Notes |
|---|---|
| `businesses` | one row per prospect; lead state (status, priority, score, opportunity tags, reasons, assignment, callbacks) lives here for single-table filtering; indexes on phone, domain, city, category, status, score, priority rank, GIN on `opportunity_types`, trigram on name |
| `business_sources` | provider records, unique `(provider, external_id)` |
| `business_contacts` | all phone numbers (raw, E.164, formats, type, source, verified, invalid), unique per business |
| `website_audits` | every audit with signals, category scores, outdated signals, facts, pages |
| `call_attempts`, `notes`, `lead_events` | activity |
| `suppression_list` | do-not-contact numbers; partial unique index on active phone |
| `jobs`, `job_businesses`, `search_queries` | background jobs and their results |
| `api_usage`, `provider_cache` | cost tracking and caching |
| `app_settings`, `niche_presets`, `calling_sessions`, `import_batches`, `users` | configuration and workflow |

## Authentication

`AUTH_MODE=none` makes every request act as a seeded default user (internal/VPN use).
`AUTH_MODE=token`: users are created with `python -m app.cli create-user`, which prints a
random token (only its SHA-256 is stored). `POST /api/auth/login` exchanges it for a signed,
httpOnly session cookie; the raw token also works as `Authorization: Bearer`. All lead
records already carry `created_by_id`, `assigned_to_id` and `last_contacted_by_id`, so a
full identity provider can be added without schema changes.

## Frontend

* Routing: React Router (data router), lazy-loaded heavy pages.
* Server state: TanStack Query; list filters live in the URL (`lib/lead-query.ts`), so views
  are shareable and the back button works.
* Forms: React Hook Form + Zod (search, calling session, templates, settings, login).
* UI: shadcn/ui components on Radix primitives, Tailwind v4 tokens (`src/index.css`),
  light/dark themes.
* Types: `@leadtracker/shared` (generated) — changing a backend schema and forgetting
  `pnpm gen:api` fails CI.
