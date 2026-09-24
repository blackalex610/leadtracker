#!/bin/sh
set -e
# Run database migrations before starting when RUN_MIGRATIONS=true
# (enable it on exactly one service, e.g. the API, not the worker).
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi
exec "$@"
