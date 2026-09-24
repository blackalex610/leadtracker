# Backend image (API and worker). Build from the repository root:
#   docker build -f docker/api.Dockerfile -t leadtracker-api .
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh

RUN chmod +x /usr/local/bin/api-entrypoint.sh \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app
USER app

# FORWARDED_ALLOW_IPS: which proxies may set X-Forwarded-For/Proto (client IPs feed the
# rate limiter). "*" suits platforms where the container is only reachable through the
# platform's router; set it to your proxy's IP if the container is directly exposed.
ENV PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=production \
    LOG_JSON=true \
    FORWARDED_ALLOW_IPS="*"
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)" || exit 1

ENTRYPOINT ["api-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
