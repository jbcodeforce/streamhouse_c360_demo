#!/usr/bin/env bash
# Waits for the Connect REST API, applies the postgres-cdc connector with an
# idempotent PUT (same config as start_debezium.sh) and waits for RUNNING.
# Runs inside the one-shot `debezium-connector` compose service.
set -euo pipefail

CONNECT_URL="${CONNECT_URL:-http://debezium:8083}"
CONNECTOR_NAME="${CONNECTOR_NAME:-postgres-cdc}"
SR_AUTH="${SCHEMA_REGISTRY_API_KEY}:${SCHEMA_REGISTRY_API_SECRET}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "Waiting for the Connect REST API at ${CONNECT_URL} ..."
for _ in $(seq 1 60); do
  curl -fs --max-time 2 "${CONNECT_URL}/connector-plugins" 2>/dev/null | grep -q PostgresConnector && break
  sleep 2
done
curl -fs --max-time 2 "${CONNECT_URL}/connector-plugins" | grep -q PostgresConnector \
  || { log "ERROR: Connect REST API not ready"; exit 1; }

log "Applying connector '${CONNECTOR_NAME}' ..."
code="$(curl -s -o /tmp/resp.json -w '%{http_code}' -X PUT \
  "${CONNECT_URL}/connectors/${CONNECTOR_NAME}/config" \
  -H "Content-Type: application/json" --data-binary @- <<EOF
{
  "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
  "tasks.max": "1",
  "database.hostname": "${PG_HOST}",
  "database.port": "5432",
  "database.user": "${PG_USER}",
  "database.password": "${PG_PASSWORD}",
  "database.dbname": "${PG_DB}",
  "plugin.name": "pgoutput",
  "publication.name": "${PG_PUBLICATION}",
  "publication.autocreate.mode": "disabled",
  "slot.name": "${PG_SLOT}",
  "table.include.list": "public.accounts,public.cards,public.customers,public.transactions",
  "snapshot.mode": "initial",
  "tombstones.on.delete": "true",
  "topic.prefix": "cdc",
  "topic.creation.enable": "true",
  "topic.creation.default.replication.factor": "3",
  "topic.creation.default.partitions": "6",
  "topic.creation.default.cleanup.policy": "delete",
  "key.converter": "io.confluent.connect.avro.AvroConverter",
  "key.converter.schema.registry.url": "${SCHEMA_REGISTRY_URL}",
  "key.converter.basic.auth.credentials.source": "USER_INFO",
  "key.converter.basic.auth.user.info": "${SR_AUTH}",
  "value.converter": "io.confluent.connect.avro.AvroConverter",
  "value.converter.schema.registry.url": "${SCHEMA_REGISTRY_URL}",
  "value.converter.basic.auth.credentials.source": "USER_INFO",
  "value.converter.basic.auth.user.info": "${SR_AUTH}"
}
EOF
)"
if [[ "${code}" != "200" && "${code}" != "201" ]]; then
  log "ERROR: connector request failed (HTTP ${code})"
  cat /tmp/resp.json >&2
  exit 1
fi

for _ in $(seq 1 30); do
  status="$(curl -s "${CONNECT_URL}/connectors/${CONNECTOR_NAME}/status" | tr -d ' \n')"
  if [[ "${status}" == *'"tasks":[{"id":0,"state":"RUNNING"'* ]]; then
    log "Connector '${CONNECTOR_NAME}' is RUNNING."
    exit 0
  fi
  if [[ "${status}" == *'"state":"FAILED"'* ]]; then
    log "Connector failed (is the c360_cdc_publication created? run the backend bootstrap). Retrying ..."
    exit 1
  fi
  sleep 2
done
log "ERROR: connector did not reach RUNNING in time"
exit 1
