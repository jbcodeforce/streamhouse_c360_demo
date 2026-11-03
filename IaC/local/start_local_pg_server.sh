#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_pg.sh
# Starts a local PostgreSQL 17 container using the Apple Container CLI,
#
# Usage:
#   ./scripts/local-tests/start_local_pg_server.sh
#
# Options:
#   --stop          Stop and remove the running container, then exit
#   --reset         Stop + remove any existing container, start a fresh one
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


# ── Argument parsing ───────────────────────────────────────────────────────────
DO_STOP=false
DO_RESET=false


while [[ $# -gt 0 ]]; do
  case "$1" in
    --stop)       DO_STOP=true; shift ;;
    --reset)      DO_RESET=true; shift ;;
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

# ── --reset: tear down first ───────────────────────────────────────────────────
if [[ "${DO_RESET}" == true ]]; then
  log "--reset: tearing down existing container if any …"
  stop_and_remove
fi

# ── Start container (skip if already running) ─────────────────────────────────
if container_running; then
  log "Container '${CONTAINER_NAME}' is already running — skipping start."
elif container_exists; then
  err "Container '${CONTAINER_NAME}' exists but is not running."
  err "Use --reset to remove it and start fresh, or --stop to remove it."
  exit 1
else
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
fi

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
echo "    ./scripts/local-tests/start_pg.sh --stop"
echo ""

