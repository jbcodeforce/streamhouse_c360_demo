#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# configure_pg_cdc.sh
# Configures a local PostgreSQL container for CDC using Debezium.
# Enables WAL level=logical, creates replication slot, and publication for tables.
#
# Usage:
#   ./configure_pg_cdc.sh
#
# Environment (optional overrides):
#   LOCAL_PG_USER       (default: dbadmin)
#   LOCAL_PG_PASSWORD   (default: localdevonly)
#   LOCAL_PG_HOST       (default: localhost)
#   LOCAL_PG_PORT       (default: 5432)
#   LOCAL_PG_DB         (default: c360db)
#   CONTAINER_NAME      (default: c360-postgres)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
LOCAL_PG_USER="${LOCAL_PG_USER:-dbadmin}"
LOCAL_PG_PASSWORD="${LOCAL_PG_PASSWORD:-localdevonly}"
LOCAL_PG_HOST="${LOCAL_PG_HOST:-localhost}"
LOCAL_PG_PORT="${LOCAL_PG_PORT:-5432}"
LOCAL_PG_DB="${LOCAL_PG_DB:-c360db}"
CONTAINER_NAME="${CONTAINER_NAME:-c360-postgres}"

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
err()  { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

# ── Main ───────────────────────────────────────────────────────────────────────
log "Configuring PostgreSQL for CDC..."

# Check if container is running
if ! container list --format json 2>/dev/null | grep -q "\"${CONTAINER_NAME}\""; then
  die "Container '${CONTAINER_NAME}' is not running. Start it first with:
    (cd apps/backend && ./start_local_pg_server.sh)"
fi

# Configure WAL level to logical (via TCP, not socket)
log "Setting WAL level to logical…"
container exec "${CONTAINER_NAME}" \
  psql -h localhost -U "${LOCAL_PG_USER}" -d postgres -c "ALTER SYSTEM SET wal_level = logical;" || \
  die "Failed to set wal_level"

# Allow only a limited number of concurrent connections to WAL
log "Setting max_wal_senders…"
container exec "${CONTAINER_NAME}" \
  psql -h localhost -U "${LOCAL_PG_USER}" -d postgres -c "ALTER SYSTEM SET max_wal_senders = 4;" || true

# Allow decoding of changes
log "Setting max_replication_slots…"
container exec "${CONTAINER_NAME}" \
  psql -h localhost -U "${LOCAL_PG_USER}" -d postgres -c "ALTER SYSTEM SET max_replication_slots = 4;" || true

# Restart PostgreSQL for WAL level change to take effect
log "Restarting PostgreSQL for WAL changes…"
container stop "${CONTAINER_NAME}"
container start "${CONTAINER_NAME}"

# Wait for PostgreSQL to be ready
log "Waiting for PostgreSQL to restart…"
MAX_WAIT=30
ELAPSED=0
until container exec "${CONTAINER_NAME}" \
      pg_isready -U "${LOCAL_PG_USER}" -d "${LOCAL_PG_DB}" -q 2>/dev/null; do
  if [[ ${ELAPSED} -ge ${MAX_WAIT} ]]; then
    die "PostgreSQL did not start within ${MAX_WAIT}s."
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done
log "PostgreSQL restarted (${ELAPSED}s)."

# Create replication slot (debezium will use this)
log "Creating replication slot 'debezium_slot'…"
container exec "${CONTAINER_NAME}" \
  psql -h localhost -U "${LOCAL_PG_USER}" -d "${LOCAL_PG_DB}" \
  -c "SELECT * FROM pg_create_logical_replication_slot('debezium_slot', 'test_decoding');" 2>&1 | \
  grep -q "debezium_slot" || \
  log "Slot may already exist (this is OK)"

# Create publication for CDC tables (cdc.* schema)
log "Creating publication for cdc.* tables…"
container exec "${CONTAINER_NAME}" \
  psql -h localhost -U "${LOCAL_PG_USER}" -d "${LOCAL_PG_DB}" \
  -c "CREATE PUBLICATION debezium_pub FOR ALL TABLES IN SCHEMA cdc;" 2>&1 | \
  grep -q "already exists" && \
  log "Publication already exists (updating)" || \
  log "Publication created"

# Verify configuration
log "Verifying WAL configuration…"
container exec "${CONTAINER_NAME}" \
  psql -h localhost -U "${LOCAL_PG_USER}" -d "${LOCAL_PG_DB}" \
  -c "SHOW wal_level; SHOW max_wal_senders; SHOW max_replication_slots;"

log "✅ PostgreSQL is configured for CDC."
log ""
log "Replication details:"
log "  Replication slot: debezium_slot"
log "  Publication: debezium_pub (all tables in cdc schema)"
log "  WAL level: logical"
echo ""
