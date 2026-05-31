#!/usr/bin/env bash
# Wait for the tacapes Postgres container to be ready.
set -euo pipefail
HOST="${PGHOST:-127.0.0.1}"
PORT="${PGPORT:-5433}"
USER="${PGUSER:-tacapes}"
DB="${PGDATABASE:-tacapes}"
for i in {1..30}; do
  if docker exec tacapes-db pg_isready -U "$USER" -d "$DB" -h localhost >/dev/null 2>&1; then
    echo "db ready at ${HOST}:${PORT}/${DB}"
    exit 0
  fi
  sleep 1
done
echo "db did not become ready in 30s" >&2
exit 1
