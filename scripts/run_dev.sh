#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_dev.sh
# Run the C360 backend (FastAPI/uvicorn) and frontend (Vite) together with one
# command. Validates the configuration up front and prints which database the
# backend will connect to, so you never start against the wrong one.
#
# Usage:
#   ./scripts/run_dev.sh                 # honor exported DATABASE_URL, else local
#   ./scripts/run_dev.sh --db local      # force the local PostgreSQL DSN
#   ./scripts/run_dev.sh --db rds        # AWS RDS (DATABASE_URL must be set)
#   ./scripts/run_dev.sh --db-url URL    # explicit DATABASE_URL (any target)
#   ./scripts/run_dev.sh --cdc           # local dev with CDC to Confluent Cloud
#
# Database selection (first match wins):
#   1. --db-url URL        use URL verbatim
#   2. --db rds            use $DATABASE_URL (error if unset)
#   3. --db local          use the local container DSN, ignoring $DATABASE_URL
#   4. no flag + $DATABASE_URL set   → honor it (e.g. from set_env_from_tf.sh)
#   5. no flag + unset     → local container DSN (default)
#
# To load RDS settings from Terraform first, SOURCE the helper so the exports
# reach this script (executing it in a subshell loses them):
#   source scripts/set_env_from_tf.sh && ./scripts/run_dev.sh
#
# Options:
#   --db local|rds   Force a target. Omit to auto-detect from $DATABASE_URL.
#   --db-url URL     Override DATABASE_URL explicitly (implies a custom target).
#   --cdc            Setup CDC: configure PostgreSQL + start Debezium server.
#   --no-frontend    Start the backend only.
#   --no-backend     Start the frontend only.
#   --no-debezium    When --cdc is set, skip starting Debezium (configure PG only).
#   --check          Validate + print config, then exit without starting.
#   -h, --help       Show this help.
#
# Environment overrides:
#   DATABASE_URL     Required for --db rds (a postgresql://… DSN). Read from the
#                    environment so secrets never land in a file (per repo policy).
#   BACKEND_PORT     Default: 8000
#   FRONTEND_PORT    Default: 5173
#   LOCAL_PG_*       LOCAL_PG_USER / LOCAL_PG_PASSWORD / LOCAL_PG_HOST /
#                    LOCAL_PG_PORT / LOCAL_PG_DB override the local DSN parts.
#
# Configuration file support:
#   This script automatically reads and exports variables from the .env file
#   specified by $ENV_CONFIG_FILE (or apps/backend/.env / .env if present),
#   without overriding variables already set in your calling environment.
#   CLI flags (--db, --db-url) and exported shell variables take precedence.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/apps/backend"
FRONTEND_DIR="${REPO_ROOT}/apps/frontend"
LOCAL_IAC_DIR="${REPO_ROOT}/IaC/local"

# ── Helpers ─────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
err()  { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }
warn() { echo "[$(date '+%H:%M:%S')] WARN:  $*"; }
die()  { err "$*"; exit 1; }

# Replace the password in a postgresql://user:pass@host DSN with ****.
mask_dsn() {
  echo "$1" | sed -E 's#(://[^:/@]+:)[^@]*@#\1****@#'
}

# Extract host:port/db from a DSN for a friendly one-line summary.
dsn_target() {
  echo "$1" | sed -E 's#^[^@]*@##; s#\?.*$##'
}

# Keys the script intentionally derives/overrides itself (from flags or host
# inference), so a shell value differing from the file is expected, not a mistake.
SHADOW_IGNORE_RE='^(ENV_CONFIG_FILE|DATABASE_URL|VITE_API_BASE_URL)$'
# Populated by load_dotenv: keys whose already-exported shell value differs from
# the .env file, so the file edit is silently ignored (shell env wins in both
# load_dotenv below and pydantic-settings). Printed as a warning afterward.
SHADOWED_VARS=()

# Mask values of secret-looking keys so a warning never leaks credentials.
mask_value() {
  case "$1" in
    *KEY*|*SECRET*|*PASSWORD*|*TOKEN*|*DATABASE_URL*) echo "****" ;;
    *) echo "$2" ;;
  esac
}

# Load key-values from a .env file without overriding existing environment
# variables. Records any key whose shell value shadows a differing file value.
load_dotenv() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    line="${line#export }"
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      local var_name="${BASH_REMATCH[1]}"
      local var_value="${BASH_REMATCH[2]}"
      if [[ "$var_value" =~ ^\"(.*)\"$ ]]; then
        var_value="${BASH_REMATCH[1]}"
      elif [[ "$var_value" =~ ^\'(.*)\'$ ]]; then
        var_value="${BASH_REMATCH[1]}"
      fi
      if [[ -z "${!var_name+x}" ]]; then
        export "$var_name"="$var_value"
      elif [[ "${!var_name}" != "$var_value" && ! "$var_name" =~ $SHADOW_IGNORE_RE ]]; then
        SHADOWED_VARS+=("${var_name} (shell=$(mask_value "$var_name" "${!var_name}") file=$(mask_value "$var_name" "$var_value"))")
      fi
    fi
  done < "$env_file"
}

# Print the leading comment block (everything after the shebang up to the first
# non-comment, non-blank line) as help — robust to edits that shift line numbers.
usage() {
  awk 'NR==1 && /^#!/ {next} /^#/ {sub(/^# ?/,""); print; next} /^$/ {print; next} {exit}' "${BASH_SOURCE[0]}"
}

# ── Load environment file ───────────────────────────────────────────────────
RESOLVED_ENV_FILE=""
if [[ -n "${ENV_CONFIG_FILE:-}" ]]; then
  if [[ -f "$ENV_CONFIG_FILE" ]]; then
    RESOLVED_ENV_FILE="$ENV_CONFIG_FILE"
  elif [[ -f "${REPO_ROOT}/${ENV_CONFIG_FILE}" ]]; then
    RESOLVED_ENV_FILE="${REPO_ROOT}/${ENV_CONFIG_FILE}"
  elif [[ -f "${BACKEND_DIR}/${ENV_CONFIG_FILE}" ]]; then
    RESOLVED_ENV_FILE="${BACKEND_DIR}/${ENV_CONFIG_FILE}"
  else
    warn "ENV_CONFIG_FILE='$ENV_CONFIG_FILE' was specified but the file was not found."
  fi
elif [[ -f "${BACKEND_DIR}/.env" ]]; then
  RESOLVED_ENV_FILE="${BACKEND_DIR}/.env"
elif [[ -f "${REPO_ROOT}/.env" ]]; then
  RESOLVED_ENV_FILE="${REPO_ROOT}/.env"
fi

if [[ -n "$RESOLVED_ENV_FILE" && -f "$RESOLVED_ENV_FILE" ]]; then
  # Guard 1: ENV_CONFIG_FILE points away from the default apps/backend/.env while
  # that default also exists — edits to .env are then silently ignored. The
  # resolved paths are compared by basename+size-independent realpath where
  # available, else by string, to tolerate the "/./" relative forms.
  DEFAULT_ENV_FILE="${BACKEND_DIR}/.env"
  if [[ -f "$DEFAULT_ENV_FILE" ]]; then
    _resolved_real="$(cd "$(dirname "$RESOLVED_ENV_FILE")" 2>/dev/null && echo "$(pwd)/$(basename "$RESOLVED_ENV_FILE")")"
    _default_real="$(cd "$(dirname "$DEFAULT_ENV_FILE")" 2>/dev/null && echo "$(pwd)/$(basename "$DEFAULT_ENV_FILE")")"
    if [[ "$_resolved_real" != "$_default_real" ]]; then
      warn "ENV_CONFIG_FILE points at '$RESOLVED_ENV_FILE', so the default"
      warn "  '$DEFAULT_ENV_FILE' is NOT loaded — edits there are ignored."
      warn "  Run 'unset ENV_CONFIG_FILE' (and remove it from your shell profile) to use the default."
    fi
  fi

  load_dotenv "$RESOLVED_ENV_FILE"
  export ENV_CONFIG_FILE="$RESOLVED_ENV_FILE"

  # Guard 2: shell env vars that shadow (and differ from) the .env file. Because
  # load_dotenv won't override an already-set var AND pydantic-settings ranks real
  # env vars above the env_file, these make the file edit a silent no-op.
  if (( ${#SHADOWED_VARS[@]} > 0 )); then
    warn "These variables are already set in your shell and OVERRIDE '$RESOLVED_ENV_FILE'"
    warn "  (edits to the file are ignored for them — shell wins):"
    for _v in "${SHADOWED_VARS[@]}"; do warn "    $_v"; done
    warn "  Run 'unset <NAME>' for each, or start a fresh shell, to use the file values."
  fi
fi

# ── Argument parsing ────────────────────────────────────────────────────────
DB_TARGET=""               # "" => auto-detect | local | rds | custom | env
DB_URL_OVERRIDE=""
RUN_BACKEND=true
RUN_FRONTEND=true
RUN_CDC=false
RUN_DEBEZIUM=true
CHECK_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db)          DB_TARGET="${2:-}"; shift 2 ;;
    --db=*)        DB_TARGET="${1#*=}"; shift ;;
    --db-url)      DB_URL_OVERRIDE="${2:-}"; DB_TARGET="custom"; shift 2 ;;
    --db-url=*)    DB_URL_OVERRIDE="${1#*=}"; DB_TARGET="custom"; shift ;;
    --cdc)         RUN_CDC=true; DB_TARGET="local"; shift ;;
    --no-frontend) RUN_FRONTEND=false; shift ;;
    --no-backend)  RUN_BACKEND=false; shift ;;
    --no-debezium) RUN_DEBEZIUM=false; shift ;;
    --check)       CHECK_ONLY=true; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             die "Unknown option: $1 (use --help)" ;;
  esac
done

case "$DB_TARGET" in
  ""|local|rds|custom) ;;
  *) die "--db must be 'local' or 'rds' (got '$DB_TARGET')" ;;
esac

# No explicit flag: honor an already-exported DATABASE_URL, else fall back local.
if [[ -z "$DB_TARGET" ]]; then
  if [[ -n "${DATABASE_URL:-}" ]]; then
    DB_TARGET="env"
  else
    DB_TARGET="local"
  fi
fi

$RUN_BACKEND || $RUN_FRONTEND || die "Nothing to run: --no-backend and --no-frontend are mutually exclusive."

# ── Resolve configuration ───────────────────────────────────────────────────
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

LOCAL_PG_USER="${LOCAL_PG_USER:-dbadmin}"
LOCAL_PG_PASSWORD="${LOCAL_PG_PASSWORD:-localdevonly}"
LOCAL_PG_HOST="${LOCAL_PG_HOST:-localhost}"
LOCAL_PG_PORT="${LOCAL_PG_PORT:-5432}"
LOCAL_PG_DB="${LOCAL_PG_DB:-c360db}"
LOCAL_DSN="postgresql://${LOCAL_PG_USER}:${LOCAL_PG_PASSWORD}@${LOCAL_PG_HOST}:${LOCAL_PG_PORT}/${LOCAL_PG_DB}"

DB_LABEL=""
case "$DB_TARGET" in
  local)
    RESOLVED_DSN="$LOCAL_DSN"
    DB_LABEL="Local PostgreSQL (container from IaC/local/start_local_pg_server.sh)"
    ;;
  rds)
    RESOLVED_DSN="${DATABASE_URL:-}"
    [[ -n "$RESOLVED_DSN" ]] || die "--db rds requires DATABASE_URL to be exported (never hard-coded here).
         Load it from Terraform first:  source scripts/set_env_from_tf.sh
         or export manually:  export DATABASE_URL='postgresql://dbadmin:<pwd>@<rds-endpoint>:5432/c360db'"
    DB_LABEL="AWS RDS PostgreSQL"
    ;;
  env)
    RESOLVED_DSN="$DATABASE_URL"
    case "$(dsn_target "$RESOLVED_DSN")" in
      *rds.amazonaws.com*) DB_LABEL="AWS RDS PostgreSQL (from \$DATABASE_URL)" ;;
      localhost*|127.0.0.1*) DB_LABEL="Local PostgreSQL (from \$DATABASE_URL)" ;;
      *)                   DB_LABEL="From environment \$DATABASE_URL" ;;
    esac
    ;;
  custom)
    RESOLVED_DSN="$DB_URL_OVERRIDE"
    DB_LABEL="Custom target (--db-url)"
    ;;
esac

# ── Validation ──────────────────────────────────────────────────────────────
log "Validating configuration…"

[[ "$RESOLVED_DSN" == postgresql://* || "$RESOLVED_DSN" == postgres://* ]] \
  || die "DATABASE_URL does not look like a postgresql:// DSN: $(mask_dsn "$RESOLVED_DSN")"

if $RUN_BACKEND; then
  [[ -d "$BACKEND_DIR" ]]       || die "Backend directory not found: $BACKEND_DIR"
  command -v uv >/dev/null 2>&1 || die "'uv' not found on PATH — install it (https://docs.astral.sh/uv/) to run the backend."
  # Ensure the backend venv matches pyproject/uv.lock before launch. Without this
  # an out-of-sync venv missing the uvicorn entry point lets 'uv run uvicorn' fall
  # through PATH to a stranger's uvicorn (e.g. a system Python with no psycopg2).
  log "Syncing backend dependencies (uv sync)…"
  ( cd "$BACKEND_DIR" && uv sync ) || die "uv sync failed in $BACKEND_DIR"
fi

if $RUN_FRONTEND; then
  [[ -d "$FRONTEND_DIR" ]]       || die "Frontend directory not found: $FRONTEND_DIR"
  command -v npm >/dev/null 2>&1 || die "'npm' not found on PATH — install Node.js to run the frontend."
fi

# CDC validation
if $RUN_CDC; then
  [[ -x "$LOCAL_IAC_DIR/configure_pg_cdc.sh" ]] \
    || die "CDC setup script not found: $LOCAL_IAC_DIR/configure_pg_cdc.sh"
  if $RUN_DEBEZIUM; then
    [[ -x "$LOCAL_IAC_DIR/start_debezium.sh" ]] \
      || die "Debezium startup script not found: $LOCAL_IAC_DIR/start_debezium.sh"
    [[ -n "${CONFLUENT_CLOUD_API_KEY:-}${CONFLUENT_CLOUD_BOOTSTRAP_SERVER:-}" ]] || \
      warn "Confluent Cloud credentials not found. Add CONFLUENT_CLOUD_API_KEY, CONFLUENT_CLOUD_API_SECRET, and CONFLUENT_CLOUD_BOOTSTRAP_SERVER to backend/.env"
  fi
fi

# Reachability check for the local DB (best effort; warn only).
if $RUN_BACKEND && [[ "$DB_TARGET" == "local" ]]; then
  if command -v nc >/dev/null 2>&1 && ! nc -z "$LOCAL_PG_HOST" "$LOCAL_PG_PORT" >/dev/null 2>&1; then
    warn "No PostgreSQL listening on ${LOCAL_PG_HOST}:${LOCAL_PG_PORT}."
    if $RUN_CDC; then
      warn "Start PostgreSQL with CDC enabled:  (cd IaC/local && ./start_local_pg_server.sh && ./configure_pg_cdc.sh)"
    else
      warn "Start it first:  (cd IaC/local && ./start_local_pg_server.sh)"
    fi
  fi
fi

VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:${BACKEND_PORT}/api/v1}"

# ── Export environment for child processes ──────────────────────────────────
if [[ -n "${ENV_CONFIG_FILE:-}" ]]; then
  export ENV_CONFIG_FILE
fi
export DATABASE_URL="$RESOLVED_DSN"
export VITE_API_BASE_URL

# ── Summary ─────────────────────────────────────────────────────────────────
echo
echo "─────────────────────────────────────────────────────────────"
echo "  C360 dev stack"
echo "─────────────────────────────────────────────────────────────"
printf '  %-14s %s\n' "CONFIG FILE:" "${RESOLVED_ENV_FILE:-(none)}"
$RUN_BACKEND  && printf '  %-14s %s\n' "BACKEND:"  "http://localhost:${BACKEND_PORT}  (docs: /docs)"
$RUN_FRONTEND && printf '  %-14s %s\n' "FRONTEND:" "http://localhost:${FRONTEND_PORT}"
$RUN_FRONTEND && printf '  %-14s %s\n' "API base:" "$VITE_API_BASE_URL"
$RUN_CDC      && printf '  %-14s %s\n' "CDC:"      "PostgreSQL → Debezium → Confluent Cloud"
$RUN_CDC && $RUN_DEBEZIUM && printf '  %-14s %s\n' "Debezium REST:" "http://localhost:8083"
echo "─────────────────────────────────────────────────────────────"
echo

if $RUN_BACKEND; then
  ( cd "$BACKEND_DIR" && uv run python -c "from config import settings; settings.log_summary()" )
  echo
fi

if $CHECK_ONLY; then
  log "Configuration OK (--check): nothing started."
  exit 0
fi

# ── CDC Setup ───────────────────────────────────────────────────────────────
if $RUN_CDC; then
  log "Setting up CDC pipeline…"

  log "Configuring PostgreSQL for CDC…"
  ( cd "$LOCAL_IAC_DIR" && exec bash configure_pg_cdc.sh ) || \
    die "Failed to configure PostgreSQL for CDC"

  if $RUN_DEBEZIUM; then
    log "Starting Debezium server…"
    ( cd "$LOCAL_IAC_DIR" && bash start_debezium.sh ) || \
      die "Failed to start Debezium server"
    log "Debezium is ready. CDC events from cdc.* tables will flow to Confluent Cloud."
  else
    log "PostgreSQL configured for CDC (Debezium start skipped via --no-debezium)"
  fi
fi

# ── Launch ──────────────────────────────────────────────────────────────────

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  trap - INT TERM EXIT
  echo
  log "Shutting down…"
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  if [[ -n "$BACKEND_PID" ]]; then
    pkill -P "$BACKEND_PID" 2>/dev/null || true   # uvicorn --reload child
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

if $RUN_BACKEND; then
  log "Starting backend on :${BACKEND_PORT} …"
  # 'python -m uvicorn' (not 'uv run uvicorn'): python always resolves to the venv
  # interpreter, so uvicorn loads from that interpreter's packages and can never
  # fall through PATH to a system-wide uvicorn with different/missing deps.
  ( cd "$BACKEND_DIR" && exec uv run python -m uvicorn main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" ) &
  BACKEND_PID=$!
fi

if $RUN_FRONTEND; then
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    log "frontend/node_modules missing — running 'npm install' …"
    ( cd "$FRONTEND_DIR" && npm install )
  fi
  log "Starting frontend on :${FRONTEND_PORT} …"
  ( cd "$FRONTEND_DIR" && exec npm run dev -- --port "$FRONTEND_PORT" ) &
  FRONTEND_PID=$!
fi

log "Both services launched. Press Ctrl-C to stop."

# Bash 3.2 has no 'wait -n'; poll until either child exits, then tear down.
while :; do
  if [[ -n "$BACKEND_PID" ]] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    err "Backend exited."; break
  fi
  if [[ -n "$FRONTEND_PID" ]] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    err "Frontend exited."; break
  fi
  sleep 1
done
