# Deployment

## Components

Two supported shapes: **Vercel all-in-one** (static web app + the FastAPI backend as one
Python function + Neon Postgres) and **containers** (API, worker, web).

| Component | Image / artifact | Scaling |
|---|---|---|
| API | `docker/api.Dockerfile` → `uvicorn app.main:app` | stateless, any number of replicas |
| Worker | same image → `python -m app.worker` | any number; jobs are claimed with `SKIP LOCKED` |
| Web | `apps/web` static build (Vercel) or `docker/web.Dockerfile` (nginx) | static |
| Database | managed PostgreSQL 14+ with `pg_trgm` available | — |

Small deployments can run a single API container with `RUN_WORKER=true` (the default).

## Environment (production)

```env
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME
PROVIDER_API_KEY=...            # Google Places API (New)
AUTH_MODE=token
SECRET_KEY=...                  # python -c "import secrets; print(secrets.token_urlsafe(48))"
SESSION_COOKIE_SECURE=true
RUN_MIGRATIONS=true             # on the API only
RUN_WORKER=false                # when a separate worker service runs
CORS_ORIGINS=https://leads.example.com   # only if the frontend calls the API cross-origin
```

Plain `postgres://…` / `postgresql://…?sslmode=require` URLs from managed providers are
converted automatically to the `postgresql+asyncpg://…?ssl=require` form the app uses.

## Render / Railway / Fly.io (container platforms)

1. Create a PostgreSQL instance; copy its URL into `DATABASE_URL`.
2. **Web service** from `docker/api.Dockerfile` (build context: repo root), port 8000,
   health check `/api/health`, env as above with `RUN_MIGRATIONS=true`.
3. **Background worker** from the same Dockerfile, start command
   `python -m app.worker`, same env but `RUN_MIGRATIONS=false`.
4. Open a shell in the API service and create users:
   `python -m app.cli create-user --email you@example.com --name "You" --admin`.

## Vercel (all-in-one)

`vercel.json` at the repository root builds the web app (`apps/web/dist`, served
statically with an SPA fallback) and deploys `api/index.py` — the whole FastAPI app
from `apps/api` — as one Python function behind `/api/*` (region `fra1`,
`maxDuration` 300 s, which needs Fluid compute — the default for new projects).
Python dependencies come from `api/requirements.txt`, generated from `apps/api/uv.lock`
(`make vercel-requirements`; CI checks it is current).

**Setup**

1. Import the repository at <https://vercel.com/new>; Root Directory `./`, preset *Other*.
2. Storage → Create → **Neon**, region Frankfurt, connected to Production and Preview.
   The app prefers `DATABASE_URL_UNPOOLED` (direct connection; advisory locks and
   `SKIP LOCKED` need a real session) and falls back to `DATABASE_URL`/`POSTGRES_URL`.
   Pooled URLs also work (prepared statements are made pooler-safe).
3. Environment variables: `AUTH_MODE=token`, `SECRET_KEY` (≥ 32 random chars),
   `ADMIN_TOKEN` (≥ 24 chars, your sign-in token), optional `ADMIN_EMAIL`,
   `PROVIDER_API_KEY`, optional `CRON_SECRET`. On deployed environments
   `ENVIRONMENT=production` and secure cookies are the default.
4. Deploy. The first API request of a new instance applies pending migrations (under a
   Postgres advisory lock), seeds the niche templates and creates/updates the admin
   from `ADMIN_TOKEN`. Changing `ADMIN_TOKEN` and redeploying rotates it. Add more users
   from a machine with the repo: `DATABASE_URL=<Neon URL> uv run python -m app.cli create-user …`
   (run in `apps/api`).

**Background jobs without a worker process.** `SERVERLESS` is detected from `VERCEL`,
which disables the embedded worker. Jobs are processed by `POST /api/worker/run`: it
claims queued jobs and runs them until the slice budget (`WORKER_RUN_BUDGET_SECONDS`,
default 40 s, shortened when Vercel's invocation deadline is closer) is spent. A
job then stops at a safe point — between provider queries, between audits, between
rescoring batches — saves a checkpoint (`jobs.checkpoint`) and is re-queued without
using up an attempt; the next slice resumes it. The web app calls the endpoint in a
loop whenever a job is active (`apps/web/src/lib/worker-pump.ts`), and Vercel Cron
calls `GET /api/worker/cron` daily (maintenance + leftovers; requires `CRON_SECRET`).
Consequence: jobs advance while someone has the app open.

**Safety checks.** On a public deployment the API answers `503 setup_required` with a
plain explanation when the database is missing, `AUTH_MODE=none` is used without
`ALLOW_OPEN_ACCESS=true`, `SECRET_KEY` is invalid, or nobody can sign in. Values are
never echoed.

**Limits to know.** The Hobby plan is for non-commercial use (a sales team needs Pro).
Neon's free tier suspends idle compute, so the first request after a pause takes
about a second longer. Rate limits are per function instance. Vercel functions have no
fixed egress IP, so the Google key can be restricted by API but not by IP.

## Vercel (frontend only)

To serve only the web app from Vercel in front of container-hosted APIs, create a
project with Root Directory `apps/web` and this `apps/web/vercel.json`:

```json
{
  "buildCommand": "cd ../.. && npx --yes pnpm@10.33.0 --filter @leadtracker/web build",
  "installCommand": "cd ../.. && npx --yes pnpm@10.33.0 install --frozen-lockfile",
  "outputDirectory": "dist",
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://YOUR-API-HOST/api/:path*" },
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ]
}
```

Alternatively build with `VITE_API_BASE_URL=https://api.example.com`, set
`CORS_ORIGINS` to the Vercel URL, and use `SESSION_COOKIE_SAMESITE=none` +
`SESSION_COOKIE_SECURE=true` (cross-site cookies).

## Single VPS with Docker Compose

```bash
git clone <repo> && cd leadtracker
cp .env.example .env && $EDITOR .env      # set PROVIDER_API_KEY, AUTH_MODE=token, SECRET_KEY, ENVIRONMENT=production
docker compose up -d --build
docker compose exec api python -m app.cli create-user --email you@example.com --name "You" --admin
```

Put a TLS-terminating reverse proxy (Caddy, Traefik, nginx) in front of port 8080 and set
`SESSION_COOKIE_SECURE=true`. Change the Postgres password in `docker-compose.yml` for
anything internet-facing, or point `DATABASE_URL` at a managed database.

## Operations

* **Migrations:** `alembic upgrade head` (automatic with `RUN_MIGRATIONS=true`).
* **Logs:** JSON in production (`LOG_JSON`), with events such as `search_job_started`,
  `business_discovered`, `business_duplicate`, `provider_error`, `website_audit_started`,
  `website_audit_completed`, `website_audit_failed`, `lead_scored`, `export_created`,
  `call_recorded`, `job_finished`. API keys and tokens are redacted.
* **Backups:** standard Postgres backups; all state is in the database.
* **Outbound network:** the API/worker need HTTPS egress to `places.googleapis.com` and
  HTTP(S) to arbitrary public websites for audits (proxies are intentionally not used by
  the auditor).
* **Rate limits:** per-process limits protect search, audit, import and login endpoints;
  for several API replicas add a limit at the proxy as well.
