#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# create_debezium_topics.sh
# Creates the Kafka Connect metadata topics used by the local Debezium worker
# in Confluent Cloud, through the Kafka REST API (v3). Idempotent.
#
# Credentials come from apps/backend/.env (KAFKA_BOOTSTRAP_SERVERS,
# KAFKA_API_KEY, KAFKA_API_SECRET, optionally KAFKA_CLUSTER_ID) or from the
# environment. The REST endpoint is derived from KAFKA_BOOTSTRAP_SERVERS
# (same host, port 443) so it can never drift from the cluster the clients use.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ENV_FILE="${SCRIPT_DIR}/../../apps/backend/.env"

# Load KAFKA_* assignments from the backend .env without overriding variables
# that are already exported.
if [[ -f "${BACKEND_ENV_FILE}" ]]; then
  while IFS='=' read -r key value; do
    [[ "${key}" =~ ^KAFKA_[A-Z_]+$ ]] || continue
    [[ -z "${!key:-}" ]] && export "${key}=${value}"
  done < <(grep -E '^KAFKA_[A-Z_]+=.+$' "${BACKEND_ENV_FILE}" || true)
fi

for var in KAFKA_BOOTSTRAP_SERVERS KAFKA_API_KEY KAFKA_API_SECRET; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: ${var} must be set (apps/backend/.env or exported)" >&2
    exit 1
  fi
done

# "SASL_SSL://pkc-xxxx.region.aws.confluent.cloud:9092" -> host
BOOTSTRAP_HOST="${KAFKA_BOOTSTRAP_SERVERS#*://}"
BOOTSTRAP_HOST="${BOOTSTRAP_HOST%%:*}"
REST_ENDPOINT="https://${BOOTSTRAP_HOST}:443"

# Keep the API secret off the process list: hand curl its credentials via stdin-like fd.
kafka_curl() {
  curl -sS --max-time 30 \
    -K <(printf 'user = "%s:%s"\n' "${KAFKA_API_KEY}" "${KAFKA_API_SECRET}") \
    "$@"
}

if [[ -z "${KAFKA_CLUSTER_ID:-}" ]]; then
  KAFKA_CLUSTER_ID="$(kafka_curl "${REST_ENDPOINT}/kafka/v3/clusters" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["cluster_id"])')"
fi

echo "Creating Debezium metadata topics on ${KAFKA_CLUSTER_ID} (${REST_ENDPOINT})..."

create_topic() {
  local topic_name=$1 partitions=$2
  local body http_code response

  body=$(printf '{"topic_name":"%s","partitions_count":%s,"replication_factor":3,"configs":[{"name":"cleanup.policy","value":"compact"}]}' \
    "${topic_name}" "${partitions}")

  response=$(kafka_curl -X POST \
    -H "Content-Type: application/json" \
    -d "${body}" \
    -w '\n%{http_code}' \
    "${REST_ENDPOINT}/kafka/v3/clusters/${KAFKA_CLUSTER_ID}/topics")
  http_code="${response##*$'\n'}"

  case "${http_code}" in
    201)      echo "✓ ${topic_name} created" ;;
    400|409)
      if [[ "${response}" == *"already exists"* ]]; then
        echo "✓ ${topic_name} already exists"
      else
        echo "✗ ${topic_name}: HTTP ${http_code}" >&2
        echo "${response%$'\n'*}" >&2
        exit 1
      fi ;;
    *)
      echo "✗ ${topic_name}: HTTP ${http_code}" >&2
      echo "${response%$'\n'*}" >&2
      exit 1 ;;
  esac
}

create_topic "my_connect_configs" 1
create_topic "my_connect_offsets" 25
create_topic "my_connect_status"  5

echo ""
echo "✓ Debezium topics setup complete"
