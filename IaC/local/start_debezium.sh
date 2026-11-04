#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_debezium.sh
# Runs a local Debezium (Kafka Connect) worker with Apple Container CLI.
# It reads the local PostgreSQL container's WAL and publishes Avro change events
# to Confluent Cloud (topics cdc.public.{customers,accounts,transactions}).
#
# Prerequisites:
#   1. Local PostgreSQL container running (./start_local_pg_server.sh) with
#      wal_level=logical and the c360_cdc_publication publication
#      (created by the backend bootstrap, see apps/backend/bootstrap.py).
#   2. KAFKA_* and SCHEMA_REGISTRY_* credentials in apps/backend/.env
#      (or exported).
#
# Usage:
#   ./start_debezium.sh              start worker + create/update connector
#   ./start_debezium.sh --reset      recreate the worker container (Kafka state kept)
#   ./start_debezium.sh --full-reset recreate worker AND wipe Kafka offset/config/status
#                                    topics + drop the PG replication slot so a full
#                                    re-snapshot is forced (use after resetting Postgres)
#   ./start_debezium.sh --stop       stop and remove the worker container
#   ./start_debezium.sh --logs       tail worker logs
#
# Environment (optional overrides):
#   DEBEZIUM_PORT            Host port for the Connect REST API (default: 8083)
#   DEBEZIUM_CONTAINER_NAME  Container name (default: c360-debezium)
#   PG_CONTAINER_NAME        Postgres container name (default: c360-postgres)
#   LOCAL_PG_USER/PASSWORD/DB/PORT   Postgres connection (see start_local_pg_server.sh)
#   PG_PUBLICATION           Publication to stream (default: c360_cdc_publication)
#   PG_SLOT                  Replication slot (default: debezium_slot)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ENV_FILE="${SCRIPT_DIR}/../../apps/backend/.env"

# Load assignments from the backend .env, without overriding exported variables.
if [[ -f "${BACKEND_ENV_FILE}" ]]; then
  while IFS='=' read -r key value; do
    [[ "${key}" =~ ^[A-Z0-9_]+$ ]] || continue
    [[ -z "${!key:-}" ]] && export "${key}=${value}"
  done < <(grep -E '^[A-Z0-9_]+=.+$' "${BACKEND_ENV_FILE}" || true)
fi

# ── Configuration ─────────────────────────────────────────────────────────────
DEBEZIUM_CONTAINER_NAME="${DEBEZIUM_CONTAINER_NAME:-c360-debezium}"
DEBEZIUM_IMAGE="quay.io/debezium/connect:3.0.0.Final"
DEBEZIUM_PORT="${DEBEZIUM_PORT:-8083}"
CONNECTOR_NAME="postgres-cdc"

PG_CONTAINER_NAME="${PG_CONTAINER_NAME:-c360-postgres}"
LOCAL_PG_USER="${LOCAL_PG_USER:-dbadmin}"
LOCAL_PG_PASSWORD="${LOCAL_PG_PASSWORD:-localdevonly}"
LOCAL_PG_DB="${LOCAL_PG_DB:-c360db}"
PG_PUBLICATION="${PG_PUBLICATION:-c360_cdc_publication}"
PG_SLOT="${PG_SLOT:-debezium_slot}"

# Confluent Avro converter. Not shipped in the Debezium image, so it is downloaded
# once into a cache dir and mounted as a Connect plugin. 7.8.x matches Kafka 3.8.
AVRO_CONVERTER_VERSION="7.8.11"
AVRO_CONVERTER_SHA1="b6af8bff514ab11a5f13f5e5a445169c3bf1c7a8"
AVRO_CONVERTER_URL="https://hub-downloads.confluent.io/api/plugins/confluentinc/kafka-connect-avro-converter/versions/${AVRO_CONVERTER_VERSION}/confluentinc-kafka-connect-avro-converter-${AVRO_CONVERTER_VERSION}.zip"
CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/c360-debezium"
AVRO_LIB_DIR="${CACHE_DIR}/confluentinc-kafka-connect-avro-converter-${AVRO_CONVERTER_VERSION}/lib"

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
err()  { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }
warn() { echo "[$(date '+%H:%M:%S')] WARN:  $*"; }
die()  { err "$*"; exit 1; }

container_exists() {
  container list --all --format json 2>/dev/null | grep -q "\"${DEBEZIUM_CONTAINER_NAME}\""
}

container_running() {
  container list --format json 2>/dev/null | grep -q "\"${DEBEZIUM_CONTAINER_NAME}\""
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
DO_FULL_RESET=false
DO_LOGS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stop)        DO_STOP=true; shift ;;
    --reset)       DO_RESET=true; shift ;;
    --full-reset)  DO_FULL_RESET=true; DO_RESET=true; shift ;;
    --logs)        DO_LOGS=true; shift ;;
    *)             err "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ "${DO_LOGS}" == true ]]; then
  if container_running; then
    exec container logs -f "${DEBEZIUM_CONTAINER_NAME}"
  fi
  exec container logs "${DEBEZIUM_CONTAINER_NAME}"
fi

if [[ "${DO_STOP}" == true ]]; then
  if container_exists; then
    stop_and_remove
    log "✅ Container '${DEBEZIUM_CONTAINER_NAME}' stopped and removed."
  else
    warn "Container '${DEBEZIUM_CONTAINER_NAME}' not found — nothing to stop."
  fi
  exit 0
fi

# ── Credentials ────────────────────────────────────────────────────────────────
for var in KAFKA_BOOTSTRAP_SERVERS KAFKA_REST_ENDPOINT KAFKA_CLUSTER_ID \
           KAFKA_API_KEY KAFKA_API_SECRET \
           SCHEMA_REGISTRY_URL SCHEMA_REGISTRY_API_KEY SCHEMA_REGISTRY_API_SECRET; do
  [[ -n "${!var:-}" ]] || die "${var} is not set. Add it to apps/backend/.env or export it."
done
BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS#*://}"

# ── Verify PostgreSQL ──────────────────────────────────────────────────────────
container list --format json 2>/dev/null | grep -q "\"${PG_CONTAINER_NAME}\"" || \
  die "PostgreSQL container '${PG_CONTAINER_NAME}' is not running.
    Start it first with:  (cd IaC/local && ./start_local_pg_server.sh)"

PG_IP="$(container list --format json | python3 -c '
import json, sys
name = sys.argv[1]
for c in json.load(sys.stdin):
    if c["configuration"]["id"] == name:
        print(c["status"]["networks"][0]["ipv4Address"].split("/")[0])
        break
' "${PG_CONTAINER_NAME}")"
[[ -n "${PG_IP}" ]] || die "Could not determine the IP address of '${PG_CONTAINER_NAME}'."

psql_pg() { container exec "${PG_CONTAINER_NAME}" psql -U "${LOCAL_PG_USER}" -d "${LOCAL_PG_DB}" -tA "$@"; }

[[ "$(psql_pg -c 'SHOW wal_level')" == "logical" ]] || \
  die "PostgreSQL wal_level is not 'logical'. Run ./configure_pg_cdc.sh or set it and restart Postgres."
[[ "$(psql_pg -c "SELECT count(*) FROM pg_publication WHERE pubname='${PG_PUBLICATION}'")" == "1" ]] || \
  die "Publication '${PG_PUBLICATION}' not found. Start the backend once
    (or run apps/backend/bootstrap.py) to create it."

# A slot created by another plugin (e.g. test_decoding) would make the connector fail.
SLOT_PLUGIN="$(psql_pg -c "SELECT plugin FROM pg_replication_slots WHERE slot_name='${PG_SLOT}'")"
if [[ -n "${SLOT_PLUGIN}" && "${SLOT_PLUGIN}" != "pgoutput" ]]; then
  die "Replication slot '${PG_SLOT}' uses plugin '${SLOT_PLUGIN}', expected 'pgoutput'.
    Drop it:  container exec ${PG_CONTAINER_NAME} psql -U ${LOCAL_PG_USER} -d ${LOCAL_PG_DB} -c \"SELECT pg_drop_replication_slot('${PG_SLOT}')\""
fi

# ── Full reset: wipe Kafka-side state so the connector re-snapshots from scratch ─
if [[ "${DO_FULL_RESET}" == true ]]; then
  log "--full-reset: dropping PG replication slot '${PG_SLOT}' (if exists) …"
  psql_pg -c "SELECT pg_drop_replication_slot('${PG_SLOT}')" 2>/dev/null || true

  log "--full-reset: deleting Connect metadata topics …"
  # Use -u for Basic Auth (same as create_debezium_topics.sh's -K <(printf user=...)).
  _kafka_curl() {
    curl -sS --max-time 30 \
      -u "${KAFKA_API_KEY}:${KAFKA_API_SECRET}" \
      "$@"
  }

  for _topic in my_connect_configs my_connect_offsets my_connect_status; do
    _code="$(_kafka_curl -o /dev/null -w '%{http_code}' -X DELETE \
      "${KAFKA_REST_ENDPOINT}/kafka/v3/clusters/${KAFKA_CLUSTER_ID}/topics/${_topic}")"
    case "${_code}" in
      204) log "  deleted ${_topic}" ;;
      404) log "  ${_topic} not found — skipping" ;;
      *)   warn "  DELETE ${_topic} returned HTTP ${_code} — continuing anyway" ;;
    esac
  done

  # Brief pause so Confluent Cloud has time to fully remove the topics before
  # create_debezium_topics.sh tries to recreate them.
  sleep 3
fi

# ── Kafka Connect metadata topics (RF=3 is enforced by Confluent Cloud) ────────
log "Ensuring Connect metadata topics exist …"
"${SCRIPT_DIR}/create_debezium_topics.sh" >/dev/null

# ── Avro converter plugin ──────────────────────────────────────────────────────
if [[ ! -d "${AVRO_LIB_DIR}" ]]; then
  log "Downloading Confluent Avro converter ${AVRO_CONVERTER_VERSION} …"
  mkdir -p "${CACHE_DIR}"
  ZIP="${CACHE_DIR}/avro-converter.zip"
  curl -fsSL --max-time 300 -o "${ZIP}" "${AVRO_CONVERTER_URL}"
  [[ "$(shasum -a 1 "${ZIP}" | cut -d' ' -f1)" == "${AVRO_CONVERTER_SHA1}" ]] || \
    { rm -f "${ZIP}"; die "Avro converter checksum mismatch."; }
  unzip -q -o "${ZIP}" -d "${CACHE_DIR}"
  rm -f "${ZIP}"
fi

# ── Worker container ───────────────────────────────────────────────────────────
if [[ "${DO_RESET}" == true ]]; then
  log "--reset: recreating worker container …"
  stop_and_remove
elif container_exists && ! container_running; then
  log "Removing stopped container '${DEBEZIUM_CONTAINER_NAME}' (state lives in Kafka) …"
  stop_and_remove
fi

if container_running; then
  log "Container '${DEBEZIUM_CONTAINER_NAME}' is already running — skipping start."
else
  log "Pulling Debezium image (if not cached) …"
  container image pull "${DEBEZIUM_IMAGE}"

  JAAS="org.apache.kafka.common.security.plain.PlainLoginModule required username='${KAFKA_API_KEY}' password='${KAFKA_API_SECRET}';"

  log "Starting Debezium worker on port ${DEBEZIUM_PORT} …"
  # The image maps CONNECT_* variables to worker properties. Names without the
  # CONNECT_ prefix (other than the few documented ones) are ignored, so the
  # storage replication factors must be CONNECT_*. Source connectors use the
  # producer.* / admin.* client overrides, hence the per-client SASL settings.
  container run \
    --detach \
    --name "${DEBEZIUM_CONTAINER_NAME}" \
    --memory 2g \
    --publish "${DEBEZIUM_PORT}:8083" \
    --dns 8.8.8.8 \
    --dns 1.1.1.1 \
    --volume "${AVRO_LIB_DIR}:/kafka/connect/confluent-avro-converter:ro" \
    --env HEAP_OPTS="-Xms256M -Xmx1G" \
    --env BOOTSTRAP_SERVERS="${BOOTSTRAP_SERVERS}" \
    --env GROUP_ID="c360-debezium" \
    --env CONFIG_STORAGE_TOPIC="my_connect_configs" \
    --env OFFSET_STORAGE_TOPIC="my_connect_offsets" \
    --env STATUS_STORAGE_TOPIC="my_connect_status" \
    --env CONNECT_CONFIG_STORAGE_REPLICATION_FACTOR="3" \
    --env CONNECT_OFFSET_STORAGE_REPLICATION_FACTOR="3" \
    --env CONNECT_STATUS_STORAGE_REPLICATION_FACTOR="3" \
    --env CONNECT_OFFSET_STORAGE_PARTITIONS="25" \
    --env CONNECT_STATUS_STORAGE_PARTITIONS="5" \
    --env CONNECT_SECURITY_PROTOCOL="SASL_SSL" \
    --env CONNECT_SASL_MECHANISM="PLAIN" \
    --env CONNECT_SASL_JAAS_CONFIG="${JAAS}" \
    --env CONNECT_PRODUCER_SECURITY_PROTOCOL="SASL_SSL" \
    --env CONNECT_PRODUCER_SASL_MECHANISM="PLAIN" \
    --env CONNECT_PRODUCER_SASL_JAAS_CONFIG="${JAAS}" \
    --env CONNECT_ADMIN_SECURITY_PROTOCOL="SASL_SSL" \
    --env CONNECT_ADMIN_SASL_MECHANISM="PLAIN" \
    --env CONNECT_ADMIN_SASL_JAAS_CONFIG="${JAAS}" \
    --env CONNECT_CONSUMER_SECURITY_PROTOCOL="SASL_SSL" \
    --env CONNECT_CONSUMER_SASL_MECHANISM="PLAIN" \
    --env CONNECT_CONSUMER_SASL_JAAS_CONFIG="${JAAS}" \
    "${DEBEZIUM_IMAGE}" >/dev/null

  log "Waiting for the Connect REST API …"
  MAX_WAIT=90
  ELAPSED=0
  until curl -fs --max-time 2 "http://localhost:${DEBEZIUM_PORT}/connector-plugins" 2>/dev/null \
        | grep -q "PostgresConnector"; do
    if ! container_running; then
      err "Worker container exited. Last log lines:"
      container logs "${DEBEZIUM_CONTAINER_NAME}" 2>&1 | grep -E "ERROR|Caused by" | tail -5 >&2 || true
      exit 1
    fi
    if [[ ${ELAPSED} -ge ${MAX_WAIT} ]]; then
      err "Debezium did not become ready within ${MAX_WAIT}s. Check:  $0 --logs"
      exit 1
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
  done
  log "Connect REST API is ready (${ELAPSED}s)."
fi

# ── Create / update the PostgreSQL CDC connector (idempotent PUT) ──────────────
log "Applying connector '${CONNECTOR_NAME}' …"
export PG_IP LOCAL_PG_USER LOCAL_PG_PASSWORD LOCAL_PG_DB PG_PUBLICATION PG_SLOT
CONNECTOR_CONFIG="$(python3 - <<'PY'
import json, os
e = os.environ
sr_auth = f"{e['SCHEMA_REGISTRY_API_KEY']}:{e['SCHEMA_REGISTRY_API_SECRET']}"
cfg = {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "database.hostname": e["PG_IP"],
    "database.port": "5432",
    "database.user": e["LOCAL_PG_USER"],
    "database.password": e["LOCAL_PG_PASSWORD"],
    "database.dbname": e["LOCAL_PG_DB"],
    "plugin.name": "pgoutput",
    "publication.name": e["PG_PUBLICATION"],
    "publication.autocreate.mode": "disabled",
    "slot.name": e["PG_SLOT"],
    "table.include.list": "public.accounts,public.customers,public.transactions",
    "snapshot.mode": "initial",
    "tombstones.on.delete": "true",
    # Topics become <prefix>.<schema>.<table> = cdc.public.<table>
    "topic.prefix": "cdc",
    "topic.creation.enable": "true",
    "topic.creation.default.replication.factor": "3",
    "topic.creation.default.partitions": "6",
    "topic.creation.default.cleanup.policy": "delete",
}
for side in ("key", "value"):
    cfg[f"{side}.converter"] = "io.confluent.connect.avro.AvroConverter"
    cfg[f"{side}.converter.schema.registry.url"] = e["SCHEMA_REGISTRY_URL"]
    cfg[f"{side}.converter.basic.auth.credentials.source"] = "USER_INFO"
    cfg[f"{side}.converter.basic.auth.user.info"] = sr_auth
print(json.dumps(cfg))
PY
)"

HTTP_CODE="$(curl -s -o /tmp/debezium-connector-response.json -w '%{http_code}' \
  -X PUT "http://localhost:${DEBEZIUM_PORT}/connectors/${CONNECTOR_NAME}/config" \
  -H "Content-Type: application/json" --data-binary @- <<<"${CONNECTOR_CONFIG}")"
if [[ "${HTTP_CODE}" != "200" && "${HTTP_CODE}" != "201" ]]; then
  err "Connector request failed (HTTP ${HTTP_CODE}):"
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("message",""))' \
    /tmp/debezium-connector-response.json >&2 || cat /tmp/debezium-connector-response.json >&2
  exit 1
fi
rm -f /tmp/debezium-connector-response.json

# ── Wait for the connector task to be RUNNING ──────────────────────────────────
STATE=""
for _ in $(seq 1 30); do
  STATE="$(curl -s "http://localhost:${DEBEZIUM_PORT}/connectors/${CONNECTOR_NAME}/status" \
    | python3 -c '
import json, sys
try:
    s = json.load(sys.stdin)
    t = s.get("tasks") or []
    print(t[0]["state"] if t else s["connector"]["state"])
except Exception:
    print("")' 2>/dev/null || true)"
  [[ "${STATE}" == "RUNNING" || "${STATE}" == "FAILED" ]] && break
  sleep 2
done
if [[ "${STATE}" != "RUNNING" ]]; then
  err "Connector task state: ${STATE:-unknown}"
  curl -s "http://localhost:${DEBEZIUM_PORT}/connectors/${CONNECTOR_NAME}/status" \
    | python3 -c 'import json,sys; [print(t.get("trace","")[:800]) for t in json.load(sys.stdin).get("tasks",[])]' >&2 || true
  exit 1
fi
log "✅ Connector '${CONNECTOR_NAME}' is RUNNING."

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "  Connect REST API : http://localhost:${DEBEZIUM_PORT}"
echo "  PostgreSQL       : ${PG_IP}:5432/${LOCAL_PG_DB} (publication ${PG_PUBLICATION}, slot ${PG_SLOT})"
echo "  Kafka            : ${BOOTSTRAP_SERVERS}"
echo "  Topics           : cdc.public.customers, cdc.public.accounts, cdc.public.transactions"
echo ""
echo "  Status : curl -s http://localhost:${DEBEZIUM_PORT}/connectors/${CONNECTOR_NAME}/status | jq"
echo "  Logs   : $0 --logs"
echo "  Stop   : $0 --stop"
echo ""
