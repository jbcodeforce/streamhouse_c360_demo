#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_pg.sh
# Starts a local PostgreSQL 17 container using the Apple Container CLI,
# then (optionally) runs the backend's own schema + seed bootstrap against it.
#
# Usage:
#   ./scripts/local_start_pg.sh [--seed] [--stop]
#
# Every start removes any existing container first, so the database is always
# empty on startup (no volume is mounted).
#
# Options:
#   --seed          Run the backend bootstrap (create schema + CDC publication
#                   and seed from the committed CSVs) after startup
#   --customers N   Deprecated: the backend seeds a fixed CSV dataset, so N is
#                   ignored. Accepted only for backward compatibility; implies --seed
#   --stop          Stop and remove the running container, then exit
#
# Environment (optional overrides):
#   PG_PASSWORD     Postgres superuser password (default: localdevonly)
#   PG_PORT         Host port to publish (default: 5432)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
CONTAINER_NAME="c360-postgres"
PG_IMAGE="docker.io/library/postgres:17"
PG_DB="c360db"
PG_USER="dbadmin"
PG_PASSWORD="${PG_PASSWORD:-localdevonly}"
PG_PORT="${PG_PORT:-5432}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/../apps/backend" && pwd)"

# ── Argument parsing ───────────────────────────────────────────────────────────
DO_SEED=false
DO_STOP=false
NUM_CUSTOMERS=50

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed)       DO_SEED=true; shift ;;
    --customers)  DO_SEED=true; NUM_CUSTOMERS="${2:?'--customers requires a value'}"
                  echo "WARN: --customers is deprecated and ignored; the backend seeds a fixed CSV dataset." >&2
                  shift 2 ;;
    --stop)       DO_STOP=true; shift ;;
    *)            echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
err()  { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }
warn() { echo "[$(date '+%H:%M:%S')] WARN:  $*"; }

container_exists() {
  container list --all --format json 2>/dev/null \
    | grep -q "\"${CONTAINER_NAME}\""
}

container_running() {
  container list --format json 2>/dev/null \
    | grep -q "\"${CONTAINER_NAME}\""
}

stop_and_remove() {
  if container_running; then
    log "Stopping container '${CONTAINER_NAME}' …"
    container stop "${CONTAINER_NAME}"
  fi
  if container_exists; then
    log "Removing container '${CONTAINER_NAME}' …"
    container delete "${CONTAINER_NAME}"
  fi
}

# ── --stop ─────────────────────────────────────────────────────────────────────
if [[ "${DO_STOP}" == true ]]; then
  if container_exists; then
    stop_and_remove
    log "✅ Container '${CONTAINER_NAME}' stopped and removed."
  else
    warn "Container '${CONTAINER_NAME}' not found — nothing to stop."
  fi
  exit 0
fi

# ── Start container (always fresh, empty database) ────────────────────────────
# Postgres data lives only in the container's writable layer (no volume is
# mounted), so removing any existing container guarantees that every start
# begins from an empty database.
log "Ensuring a clean start: removing any existing container …"
stop_and_remove

log "Pulling image ${PG_IMAGE} (if not cached) …"
container run \
  --detach \
  --name "${CONTAINER_NAME}" \
  --publish "${PG_PORT}:5432" \
  --env "POSTGRES_DB=${PG_DB}" \
  --env "POSTGRES_USER=${PG_USER}" \
  --env "POSTGRES_PASSWORD=${PG_PASSWORD}" \
  "${PG_IMAGE}"

log "Container '${CONTAINER_NAME}' started on host port ${PG_PORT}."

# Wait for PostgreSQL to be ready
log "Waiting for PostgreSQL to accept connections …"
MAX_WAIT=30
ELAPSED=0
until container exec "${CONTAINER_NAME}" \
      pg_isready -U "${PG_USER}" -d "${PG_DB}" -q 2>/dev/null; do
  if [[ ${ELAPSED} -ge ${MAX_WAIT} ]]; then
    err "PostgreSQL did not become ready within ${MAX_WAIT}s."
    exit 1
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done
log "PostgreSQL is ready (${ELAPSED}s)."

# ── Print connection details ───────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────┐"
echo "│  Local PostgreSQL connection details                    │"
echo "├─────────────────────────────────────────────────────────┤"
printf "│  Host     : %-44s│\n" "localhost"
printf "│  Port     : %-44s│\n" "${PG_PORT}"
printf "│  Database : %-44s│\n" "${PG_DB}"
printf "│  User     : %-44s│\n" "${PG_USER}"
printf "│  Password : %-44s│\n" "${PG_PASSWORD}"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
echo "  Stop / clean up:"
echo "    ./scripts/local_start_pg.sh --stop"
echo ""

# ── Optionally run the backend bootstrap (schema + CDC publication + seed) ─────
if [[ "${DO_SEED}" == true ]]; then
  log "Running backend bootstrap (schema + CDC publication + CSV seed) …"
  (
    cd "${BACKEND_DIR}"
    DATABASE_URL="postgresql://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DB}?sslmode=disable" \
    SINK=postgres \
      uv run python bootstrap.py
  )

  log "✅ Local test environment is fully seeded and ready."
else
  log "Tip: pass --seed to also create tables and seed the committed CSV dataset."
  log "  Example: ./scripts/local_start_pg.sh --seed"
fi
