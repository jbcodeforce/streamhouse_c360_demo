#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# set_env_from_tf.sh
# Export Confluent Cloud + AWS RDS settings (incl. DATABASE_URL) from Terraform
# outputs into apps/backend/.env and the current shell (when sourced).
#
# Usage:
#   source scripts/set_env_from_tf.sh   # writes to apps/backend/.env AND exports to current shell
#   ./scripts/set_env_from_tf.sh        # writes to apps/backend/.env
# ─────────────────────────────────────────────────────────────────────────────

# Detect if the script is being sourced or executed directly.
IS_SOURCED=false
if (return 0 2>/dev/null); then
  IS_SOURCED=true
fi

# Resolve this script's own path. zsh arrays are 1-indexed so ${BASH_SOURCE[0]}
# is empty there — use zsh's %x prompt escape instead; bash uses BASH_SOURCE.
if [ -n "${ZSH_VERSION:-}" ]; then
  SCRIPT_SRC="${(%):-%x}"
else
  SCRIPT_SRC="${BASH_SOURCE[0]:-$0}"
fi

# Resolve the directories regardless of where the script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_SRC}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CCLOUD_DIR="${REPO_ROOT}/IaC/ccloud"
AWS_DIR="${REPO_ROOT}/IaC/AWS"
RTCE_DIR="${REPO_ROOT}/IaC/rtce"
BACKEND_ENV_FILE="${REPO_ROOT}/apps/backend/.env"

if [[ ! -d "${CCLOUD_DIR}" ]]; then
  echo "ERROR: cannot find IaC/ccloud at ${CCLOUD_DIR}" >&2
  $IS_SOURCED && return 1 || exit 1
fi

# ── Extract Confluent Cloud outputs ──────────────────────────────────────────
export ENVIRONMENT_ID=$(terraform -chdir="${CCLOUD_DIR}" output -raw environment_id 2>/dev/null || true)
export FLINK_ENV_ID="${ENVIRONMENT_ID}"
export CC_REGION=$(terraform -chdir="${CCLOUD_DIR}" output -raw cc_region 2>/dev/null || true)
export CLOUD_REGION="${CC_REGION}"
export CC_PROVIDER=$(terraform -chdir="${CCLOUD_DIR}" output -raw cloud_provider 2>/dev/null || true)
export CLOUD_PROVIDER=$(echo "${CC_PROVIDER}" | tr '[:upper:]' '[:lower:]')
export KAFKA_CLUSTER_ID=$(terraform -chdir="${CCLOUD_DIR}" output -raw kafka_id 2>/dev/null || true)
export KAFKA_CLUSTER_NAME=$(terraform -chdir="${CCLOUD_DIR}" output -raw kafka_name 2>/dev/null || true)
export KAFKA_API_KEY=$(terraform -chdir="${CCLOUD_DIR}" output -raw kafka_api_key_id 2>/dev/null || true)
export KAFKA_API_SECRET=$(terraform -chdir="${CCLOUD_DIR}" output -raw kafka_api_key_secret 2>/dev/null || true)
export KAFKA_BOOTSTRAP_SERVERS=$(terraform -chdir="${CCLOUD_DIR}" output -raw kafka_bootstrap_endpoint 2>/dev/null || true)
export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS#SASL_SSL://}"
export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS#PLAINTEXT://}"
export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS#SSL://}"
export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS#SASL_PLAINTEXT://}"

export FLINK_COMPUTE_POOL_ID=$(terraform -chdir="${CCLOUD_DIR}" output -raw flink_compute_pool_id 2>/dev/null || true)
export FLINK_CRM_COMPUTE_POOL_ID=$(terraform -chdir="${CCLOUD_DIR}" output -raw flink_crm_compute_pool_id 2>/dev/null || true)
# Flink API key/secret are scoped to (environment, region); sourcing them here
# keeps them matched to FLINK_ENV_ID instead of drifting to a stale environment.
export FLINK_API_KEY=$(terraform -chdir="${CCLOUD_DIR}" output -raw flink_api_key_id 2>/dev/null || true)
export FLINK_API_SECRET=$(terraform -chdir="${CCLOUD_DIR}" output -raw flink_api_key_secret 2>/dev/null || true)
export FLINK_CATALOG=$(terraform -chdir="${CCLOUD_DIR}" output -raw env_display_name 2>/dev/null || true)
export FLINK_DATABASE="${KAFKA_CLUSTER_NAME}"
if [[ -n "${CLOUD_REGION}" && -n "${CLOUD_PROVIDER}" ]]; then
  export FLINK_REST_ENDPOINT="https://flink.${CLOUD_REGION}.${CLOUD_PROVIDER}.confluent.cloud"
fi

export SCHEMA_REGISTRY_URL=$(terraform -chdir="${CCLOUD_DIR}" output -raw schema_registry_rest_endpoint 2>/dev/null || true)
export SCHEMA_REGISTRY_API_KEY=$(terraform -chdir="${CCLOUD_DIR}" output -raw schema_registry_api_key_id 2>/dev/null || true)
export SCHEMA_REGISTRY_API_SECRET=$(terraform -chdir="${CCLOUD_DIR}" output -raw schema_registry_api_key_secret 2>/dev/null || true)
export SCHEMA_REGISTRY_KEY="${SCHEMA_REGISTRY_API_KEY}"
export SCHEMA_REGISTRY_SECRET="${SCHEMA_REGISTRY_API_SECRET}"

# The RTCE/Lightning Global key lives in the separate IaC/rtce stack (applied
# after dbt creates the fct_c360_profile topic). Empty until that stack is
# applied, which is fine — the backend just reports RTCE as unconfigured.
export CONFLUENT_GLOBAL_KEY=$(terraform -chdir="${RTCE_DIR}" output -raw rtce_lightning_api_key_id 2>/dev/null || true)
export CONFLUENT_GLOBAL_SECRET=$(terraform -chdir="${RTCE_DIR}" output -raw rtce_lightning_api_key_secret 2>/dev/null || true)

# ── Extract AWS RDS outputs (if available) ───────────────────────────────────
HAVE_AWS=false
if [[ -d "${AWS_DIR}" ]]; then
  RDSHOST=$(terraform -chdir="${AWS_DIR}" output -raw rds_address 2>/dev/null || true)
  SECRET_ARN=$(terraform -chdir="${AWS_DIR}" output -raw secrets_manager_secret_arn 2>/dev/null || true)
  RDSPORT=$(terraform -chdir="${AWS_DIR}" output -raw rds_port 2>/dev/null || true)
  DBNAME=$(terraform -chdir="${AWS_DIR}" output -raw rds_database_name 2>/dev/null || true)

  if [[ -n "${SECRET_ARN}" && -n "${RDSHOST}" ]]; then
    export RDSHOST SECRET_ARN RDSPORT DBNAME
    export AWS_REGION=$(echo "${SECRET_ARN}" | cut -d: -f4)
    export DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id "${SECRET_ARN}" --query SecretString --region "${AWS_REGION}" --output text 2>/dev/null | jq -r .password 2>/dev/null || true)
    if [[ -n "${DB_PASSWORD}" ]]; then
      export DATABASE_URL="postgresql://dbadmin:${DB_PASSWORD}@${RDSHOST}:${RDSPORT}/${DBNAME}?sslmode=require"
      HAVE_AWS=true
    fi
  fi
fi

# ── Write/Update apps/backend/.env ───────────────────────────────────────────
python3 - "${BACKEND_ENV_FILE}" <<EOF
import json
import os
import re
import sys

env_path = sys.argv[1]
example_path = os.path.join(os.path.dirname(env_path), ".env.example")

if not os.path.exists(env_path):
    if os.path.exists(example_path):
        with open(example_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = ""
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)

with open(env_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

env_vars = {
    "ENVIRONMENT_ID": os.environ.get("ENVIRONMENT_ID") or None,
    "FLINK_ENV_ID": os.environ.get("FLINK_ENV_ID") or None,
    "CLOUD_REGION": os.environ.get("CLOUD_REGION") or None,
    "CLOUD_PROVIDER": os.environ.get("CLOUD_PROVIDER") or None,
    "KAFKA_CLUSTER_ID": os.environ.get("KAFKA_CLUSTER_ID") or None,
    "KAFKA_CLUSTER_NAME": os.environ.get("KAFKA_CLUSTER_NAME") or None,
    "KAFKA_BOOTSTRAP_SERVERS": os.environ.get("KAFKA_BOOTSTRAP_SERVERS") or None,
    "KAFKA_API_KEY": os.environ.get("KAFKA_API_KEY") or None,
    "KAFKA_API_SECRET": os.environ.get("KAFKA_API_SECRET") or None,
    "FLINK_COMPUTE_POOL_ID": os.environ.get("FLINK_COMPUTE_POOL_ID") or None,
    "FLINK_CRM_COMPUTE_POOL_ID": os.environ.get("FLINK_CRM_COMPUTE_POOL_ID") or None,
    "FLINK_API_KEY": os.environ.get("FLINK_API_KEY") or None,
    "FLINK_API_SECRET": os.environ.get("FLINK_API_SECRET") or None,
    "FLINK_REST_ENDPOINT": os.environ.get("FLINK_REST_ENDPOINT") or None,
    "FLINK_CATALOG": os.environ.get("FLINK_CATALOG") or None,
    "FLINK_DATABASE": os.environ.get("FLINK_DATABASE") or None,
    "SCHEMA_REGISTRY_URL": os.environ.get("SCHEMA_REGISTRY_URL") or None,
    "SCHEMA_REGISTRY_API_KEY": os.environ.get("SCHEMA_REGISTRY_API_KEY") or None,
    "SCHEMA_REGISTRY_API_SECRET": os.environ.get("SCHEMA_REGISTRY_API_SECRET") or None,
    "CONFLUENT_GLOBAL_KEY": os.environ.get("CONFLUENT_GLOBAL_KEY") or None,
    "CONFLUENT_GLOBAL_SECRET": os.environ.get("CONFLUENT_GLOBAL_SECRET") or None,
    "DATABASE_URL": os.environ.get("DATABASE_URL") or None,
}

applied_keys = set()
new_lines = []

for line in lines:
    stripped = line.strip()
    matched = False
    for k, v in env_vars.items():
        if v is None:
            continue
        if re.match(rf"^(?:#\s*)?{re.escape(k)}=(.*)$", stripped) and k not in applied_keys:
            new_lines.append(f"{k}={v}\n")
            applied_keys.add(k)
            matched = True
            break
    if not matched:
        new_lines.append(line)

for k, v in env_vars.items():
    if v is not None and k not in applied_keys:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{k}={v}\n")
        applied_keys.add(k)

with open(env_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
EOF

echo "✓ Updated ${BACKEND_ENV_FILE} from Terraform outputs."
if $HAVE_AWS; then
  echo "✓ AWS RDS credentials and DATABASE_URL configured."
else
  echo "ℹ AWS RDS outputs not found; kept existing database settings."
fi

if ! $IS_SOURCED; then
  echo "ℹ To also export these variables into your current shell, run:"
  echo "    source scripts/set_env_from_tf.sh"
fi
