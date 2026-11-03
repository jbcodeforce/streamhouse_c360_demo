#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_debezium_server.sh
# Starts a local Debezium server container using Apple Container CLI.
# Connects to local PostgreSQL and publishes CDC events to Confluent Cloud Kafka.
#
# Prerequisites:
#   1. Local PostgreSQL container running (from start_local_pg_server.sh)
#   2. PostgreSQL configured for CDC (from configure_pg_cdc.sh)
#   3. Confluent Cloud credentials in ~/.confluent/.env or ENV variables
#
# Usage:
#   ./start_debezium_server.sh
#
# Options:
#   --stop          Stop and remove the running container, then exit
#   --reset         Stop + remove any existing container, start a fresh one
#   --logs          Tail container logs and exit
#
# Environment (optional overrides):
#   DEBEZIUM_PORT           Host port for Debezium REST API (default: 8083)
#   DEBEZIUM_CONTAINER_NAME Container name (default: c360-debezium)
#   LOCAL_PG_*              PostgreSQL connection details (see start_local_pg_server.sh)
#   CONFLUENT_CLOUD_*       Confluent Cloud credentials
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Load backend environment ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ENV_FILE="${SCRIPT_DIR}/../../apps/backend/.env"
if [[ -f "${BACKEND_ENV_FILE}" ]]; then
  # Safely load only assignment lines from .env (avoid sourcing shell syntax)
  set -a
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^[A-Z_]+$ ]] && export "$key=$value"
  done < <(grep -E '^[A-Z_]+=.+$' "${BACKEND_ENV_FILE}" || true)
  set +a
fi

# ── Configuration ─────────────────────────────────────────────────────────────
DEBEZIUM_CONTAINER_NAME="${DEBEZIUM_CONTAINER_NAME:-c360-debezium}"
DEBEZIUM_IMAGE="quay.io/debezium/connect:3.0.0.Final"
DEBEZIUM_PORT="${DEBEZIUM_PORT:-8083}"
DEBEZIUM_CONFIG_DIR="${DEBEZIUM_CONFIG_DIR:-.}"

LOCAL_PG_USER="${LOCAL_PG_USER:-dbadmin}"
LOCAL_PG_PASSWORD="${LOCAL_PG_PASSWORD:-localdevonly}"
LOCAL_PG_HOST="${LOCAL_PG_HOST:-localhost}"
LOCAL_PG_PORT="${LOCAL_PG_PORT:-5432}"
LOCAL_PG_DB="${LOCAL_PG_DB:-c360db}"
PG_CONTAINER_NAME="${PG_CONTAINER_NAME:-c360-postgres}"

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
err()  { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }
warn() { echo "[$(date '+%H:%M:%S')] WARN:  $*"; }
die()  { err "$*"; exit 1; }

container_exists() {
  container list --all --format json 2>/dev/null \
    | grep -q "\"${DEBEZIUM_CONTAINER_NAME}\""
}

container_running() {
  container list --format json 2>/dev/null \
    | grep -q "\"${DEBEZIUM_CONTAINER_NAME}\""
}

stop_and_remove() {
  if container_running; then
    log "Stopping container '${DEBEZIUM_CONTAINER_NAME}' …"
    container stop "${DEBEZIUM_CONTAINER_NAME}"
  fi
  if container_exists; then
    log "Removing container '${DEBEZIUM_CONTAINER_NAME}' …"
    container delete "${DEBEZIUM_CONTAINER_NAME}"
  fi
}

# ── Argument parsing ───────────────────────────────────────────────────────────
DO_STOP=false
DO_RESET=false
DO_LOGS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stop)  DO_STOP=true; shift ;;
    --reset) DO_RESET=true; shift ;;
    --logs)  DO_LOGS=true; shift ;;
    *)       err "Unknown option: $1"; exit 1 ;;
  esac
done

# ── --logs ─────────────────────────────────────────────────────────────────────
if [[ "${DO_LOGS}" == true ]]; then
  if container_running; then
    container logs -f "${DEBEZIUM_CONTAINER_NAME}"
  else
    container logs "${DEBEZIUM_CONTAINER_NAME}"
  fi
fi

# ── --stop ─────────────────────────────────────────────────────────────────────
if [[ "${DO_STOP}" == true ]]; then
  if container_exists; then
    stop_and_remove
    log "✅ Container '${DEBEZIUM_CONTAINER_NAME}' stopped and removed."
  else
    warn "Container '${DEBEZIUM_CONTAINER_NAME}' not found — nothing to stop."
  fi
  exit 0
fi

# ── --reset ────────────────────────────────────────────────────────────────────
if [[ "${DO_RESET}" == true ]]; then
  log "--reset: tearing down existing container if any …"
  stop_and_remove
fi

# ── Verify PostgreSQL is running ───────────────────────────────────────────────
if ! container list --format json 2>/dev/null | grep -q "\"${PG_CONTAINER_NAME}\""; then
  die "PostgreSQL container '${PG_CONTAINER_NAME}' is not running.
    Start it first with:  (cd IaC/local && ./start_local_pg_server.sh)"
fi

# ── Check for Confluent Cloud credentials ──────────────────────────────────────
[[ -n "${CONFLUENT_CLOUD_API_KEY:-}" ]] || \
  die "CONFLUENT_CLOUD_API_KEY is not set. Add to backend/.env or export before running."
[[ -n "${CONFLUENT_CLOUD_API_SECRET:-}" ]] || \
  die "CONFLUENT_CLOUD_API_SECRET is not set. Add to backend/.env or export before running."
[[ -n "${KAFKA_BOOTSTRAP_SERVERS:-}" ]] || \
  die "KAFKA_BOOTSTRAP_SERVERS is not set. Add to backend/.env or export before running."
[[ -n "${SCHEMA_REGISTRY_URL:-}" ]] || \
  die "SCHEMA_REGISTRY_URL is not set. Add to backend/.env or export before running."
[[ -n "${SCHEMA_REGISTRY_API_KEY:-}" ]] || \
  die "SCHEMA_REGISTRY_API_KEY is not set. Add to backend/.env or export before running."
[[ -n "${SCHEMA_REGISTRY_API_SECRET:-}" ]] || \
  die "SCHEMA_REGISTRY_API_SECRET is not set. Add to backend/.env or export before running."

# ── Prepare Debezium configuration ────────────────────────────────────────────────
DEBEZIUM_CONFIG_BASE="${SCRIPT_DIR}/debezium-postgres.conf"
DEBEZIUM_CONFIG_FILE="/tmp/debezium-postgres-runtime.conf"

log "Preparing Debezium configuration at ${DEBEZIUM_CONFIG_FILE}…"

# Copy base config (Confluent Cloud settings passed via container environment)
cp "${DEBEZIUM_CONFIG_BASE}" "${DEBEZIUM_CONFIG_FILE}"

log "Configuration prepared."

# ── Start Debezium container ───────────────────────────────────────────────────
if container_running; then
  log "Container '${DEBEZIUM_CONTAINER_NAME}' is already running — skipping start."
elif container_exists; then
  err "Container '${DEBEZIUM_CONTAINER_NAME}' exists but is not running."
  err "Use --reset to remove it and start fresh, or --stop to remove it."
  exit 1
else
  log "Pulling Debezium image (if not cached)…"
  container image pull "${DEBEZIUM_IMAGE}"

  log "Starting Debezium server on port ${DEBEZIUM_PORT}…"
  log "CC KEY: ${CONFLUENT_CLOUD_API_KEY}, broker: ${KAFKA_BOOTSTRAP_SERVERS} SR: ${SCHEMA_REGISTRY_URL}"
  # Mount configuration and run Debezium server
  # Debezium needs to reach PostgreSQL via host.docker.internal (macOS) or the host gateway
  container run \
    --detach \
    --name "${DEBEZIUM_CONTAINER_NAME}" \
    --publish "${DEBEZIUM_PORT}:8083" \
    --volume "${DEBEZIUM_CONFIG_FILE}:/etc/debezium/config/postgres-cdc.conf" \
    --env JAVA_TOOL_OPTIONS="-Xmx1g" \
    --env BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS}" \
    --env CONNECT_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS}" \
    --env SECURITY_PROTOCOL=SASL_SSL \
    --env SASL_MECHANISM=PLAIN \
    --env SASL_USERNAME="${CONFLUENT_CLOUD_API_KEY}" \
    --env SASL_PASSWORD="${CONFLUENT_CLOUD_API_SECRET}" \
    --env CONFIG_STORAGE_TOPIC="my_connect_configs" \
    --env OFFSET_STORAGE_TOPIC="my_connect_offsets" \
    --env STATUS_STORAGE_TOPIC="my_connect_status" \
    --env CONFIG_STORAGE_REPLICATION_FACTOR="3" \
    --env OFFSET_STORAGE_REPLICATION_FACTOR="3" \
    --env STATUS_STORAGE_REPLICATION_FACTOR="3" \
    --env KEY_CONVERTER_SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL}" \
    --env VALUE_CONVERTER_SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL}" \
    --env CONNECT_KEY_CONVERTER_SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL}" \
    --env CONNECT_VALUE_CONVERTER_SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL}" \
    --env SCHEMA_REGISTRY_USER="${SCHEMA_REGISTRY_API_KEY}" \
    --env SCHEMA_REGISTRY_PASSWORD="${SCHEMA_REGISTRY_API_SECRET}" \
    "${DEBEZIUM_IMAGE}"

  log "Container '${DEBEZIUM_CONTAINER_NAME}' started on http://localhost:${DEBEZIUM_PORT}"

  # Wait for Debezium REST API to be ready
  log "Waiting for Debezium to accept connections…"
  MAX_WAIT=45
  ELAPSED=0
  while ! curl -s "http://localhost:${DEBEZIUM_PORT}" >/dev/null 2>&1; do
    if [[ ${ELAPSED} -ge ${MAX_WAIT} ]]; then
      err "Debezium did not start within ${MAX_WAIT}s."
      err "Check logs with:  ./start_debezium_server.sh --logs"
      exit 1
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
  done
  log "Debezium is ready (${ELAPSED}s)."
fi

# ── Print connection details ───────────────────────────────────────────────────
echo ""
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  Debezium Server Running                                     │"
echo "├──────────────────────────────────────────────────────────────┤"
printf "│  REST API      : %-49s│\n" "http://localhost:${DEBEZIUM_PORT}"
printf "│  PostgreSQL    : %-49s│\n" "${LOCAL_PG_HOST}:${LOCAL_PG_PORT}"
printf "│  Kafka cluster : %-49s│\n" "${KAFKA_BOOTSTRAP_SERVERS}"
printf "│  Table pattern : %-49s│\n" "cdc.*"
echo "├──────────────────────────────────────────────────────────────┤"
echo "│  Next steps:                                                 │"
echo "│  1. Verify cdc.public.customers, cdc.public.accounts, cdc.public.transactions    │"
echo "│  2. Insert test data to see CDC in action                    │"
echo "│  3. Check topics in Confluent Cloud console                  │"
echo "└──────────────────────────────────────────────────────────────┘"
echo ""
echo "  Monitor logs:"
echo "    ./start_debezium_server.sh --logs"
echo ""
echo "  Stop / clean up:"
echo "    ./start_debezium_server.sh --stop"
echo ""
