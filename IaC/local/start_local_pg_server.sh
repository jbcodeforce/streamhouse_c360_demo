#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_local_pg_server.sh
# Starts a local PostgreSQL 17 container (CDC-ready: wal_level=logical) using
# the Apple Container CLI, then (optionally) runs the backend's own schema +
# seed bootstrap against it.
#
# Usage:
#   ./IaC/local/start_local_pg_server.sh [--seed] [--reset] [--stop]
#
# Options:
#   --seed          Run the backend bootstrap (create schema + CDC publication
#                   and seed from the committed CSVs) once Postgres is ready.
#                   Idempotent: safe to combine with an already-running container
#   --stop          Stop and remove the container, then exit. The data volume
#                   is kept, so the next start finds the same databases
#   --reset         Stop + remove the container AND its data volume, then start
#                   a fresh, empty one (data is lost)
#   --purge         Stop + remove the container and the data volume, then exit
#
# Environment (optional overrides):
#   PG_PASSWORD     Postgres superuser password (default: localdevonly)
#   PG_PORT         Host port to publish (default: 5432)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
CONTAINER_NAME="c360-postgres"
VOLUME_NAME="c360-pgdata"
# PGDATA is a subdirectory of the mount: a fresh volume may hold lost+found,
# which makes initdb refuse a non-empty data root.
PG_DATA_MOUNT="/var/lib/postgresql/data"
PG_IMAGE="docker.io/library/postgres:17"
PG_DB="c360db"
PG_USER="dbadmin"
PG_PASSWORD="${PG_PASSWORD:-localdevonly}"
PG_PORT="${PG_PORT:-5432}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/../../apps/backend" && pwd)"

# ── Argument parsing ───────────────────────────────────────────────────────────
DO_SEED=false
DO_STOP=false
DO_RESET=false
DO_PURGE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed)       DO_SEED=true; shift ;;
    --stop)       DO_STOP=true; shift ;;
    --reset)      DO_RESET=true; shift ;;
    --purge)      DO_PURGE=true; shift ;;
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

volume_exists() {
  container volume list --format json 2>/dev/null \
    | grep -q "\"${VOLUME_NAME}\""
}

remove_volume() {
  if volume_exists; then
    log "Removing data volume '${VOLUME_NAME}' …"
    container volume delete "${VOLUME_NAME}"
  fi
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

wait_for_postgres() {
  log "Waiting for PostgreSQL to accept connections …"
  local max_wait=30 elapsed=0
  until container exec "${CONTAINER_NAME}" \
        pg_isready -U "${PG_USER}" -d "${PG_DB}" -q 2>/dev/null; do
    if [[ ${elapsed} -ge ${max_wait} ]]; then
      err "PostgreSQL did not become ready within ${max_wait}s."
      exit 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  log "PostgreSQL is ready (${elapsed}s)."
}

# ── --stop ─────────────────────────────────────────────────────────────────────
if [[ "${DO_STOP}" == true ]]; then
  if container_exists; then
    stop_and_remove
    log "✅ Container '${CONTAINER_NAME}' stopped and removed (data volume '${VOLUME_NAME}' kept)."
  else
    warn "Container '${CONTAINER_NAME}' not found — nothing to stop."
  fi
  exit 0
fi

# ── --purge: remove container and data ─────────────────────────────────────────
if [[ "${DO_PURGE}" == true ]]; then
  stop_and_remove
  remove_volume
  log "✅ Container and data volume removed."
  exit 0
fi

# ── --reset: tear down first ───────────────────────────────────────────────────
if [[ "${DO_RESET}" == true ]]; then
  log "--reset: tearing down existing container if any …"
  stop_and_remove
  remove_volume
fi

# ── Start container (skip if already running) ─────────────────────────────────
if container_running; then
  log "Container '${CONTAINER_NAME}' is already running — skipping start."
elif container_exists; then
  log "Container '${CONTAINER_NAME}' exists but is stopped — starting it (data preserved) …"
  container start "${CONTAINER_NAME}"
  wait_for_postgres
else
  if ! volume_exists; then
    log "Creating data volume '${VOLUME_NAME}' …"
    container volume create "${VOLUME_NAME}"
  fi
  log "Pulling image ${PG_IMAGE} (if not cached) …"
  container run \
    --detach \
    --name "${CONTAINER_NAME}" \
    --publish "${PG_PORT}:5432" \
    --volume "${VOLUME_NAME}:${PG_DATA_MOUNT}" \
    --env "PGDATA=${PG_DATA_MOUNT}/pgdata" \
    --env "POSTGRES_DB=${PG_DB}" \
    --env "POSTGRES_USER=${PG_USER}" \
    --env "POSTGRES_PASSWORD=${PG_PASSWORD}" \
    "${PG_IMAGE}" \
    postgres \
      -c wal_level=logical \
      -c max_wal_senders=4 \
      -c max_replication_slots=4

  log "Container '${CONTAINER_NAME}' started on host port ${PG_PORT}."

  wait_for_postgres
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
echo "  Stop (keeps data) / wipe data:"
echo "    ./IaC/local/start_local_pg_server.sh --stop"
echo "    ./IaC/local/start_local_pg_server.sh --purge"
echo ""

# ── Optionally run the backend bootstrap (schema + CDC publication + seed) ─────
if [[ "${DO_SEED}" == true ]]; then
  log "Running backend bootstrap (schema + CDC publication + CSV seed) …"
  (
    cd "${BACKEND_DIR}"
    DATABASE_URL="postgresql://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DB}?sslmode=disable" \
      uv run python bootstrap.py
  )

  log "✅ Local database is fully seeded and ready."
else
  log "Tip: pass --seed to also create tables and seed the committed CSV dataset."
  log "  Example: ./IaC/local/start_local_pg_server.sh --seed"
fi
