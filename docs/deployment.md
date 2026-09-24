# Deployment

## Components

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

## Vercel (frontend)

* Root directory: `apps/web` (uses `apps/web/vercel.json`; installs the pnpm workspace).
* Add the API rewrite **first** so the browser stays on one origin:

```json
{
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
