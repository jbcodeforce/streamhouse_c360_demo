#!/usr/bin/env bash
#
# Idempotent deploy for the C360 stack on EC2. Installed as /usr/local/bin/c360-deploy
# by Terraform user_data (see IaC/EC2/ec2.tf); re-run it any time to redeploy:
#   sudo c360-deploy
#
# Steps: sync the repo -> render backend.env from AWS Secrets Manager (instance
# role) -> docker compose up -d --build. Secrets are never written to user_data,
# git, or logs.
#
# Environment (set in /etc/c360-deploy.env by user_data):
#   REPO_URL, REPO_REF, AWS_REGION, RDS_SECRET_ARN, APP_SECRET_ID
set -euo pipefail

source /etc/c360-deploy.env

APP_DIR=/opt/c360
ENV_FILE="${APP_DIR}/deploy/backend.env"

# ── 1. Repo ──────────────────────────────────────────────────────────────────
if [[ -d "${APP_DIR}/.git" ]]; then
  git -C "${APP_DIR}" fetch --depth 1 origin "${REPO_REF}"
  git -C "${APP_DIR}" checkout --force FETCH_HEAD
else
  rm -rf "${APP_DIR}"
  git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" "${APP_DIR}"
fi

# ── 2. backend.env from Secrets Manager ──────────────────────────────────────
# RDS secret JSON {host,port,username,password,database} -> DATABASE_URL (the
# password is percent-encoded). App secret JSON {ENV_VAR: value, ...} -> KEY=value.
umask 077
python3 - "${ENV_FILE}" <<'PY'
import json, os, subprocess, sys
from urllib.parse import quote

def secret(secret_id):
    out = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--region", os.environ["AWS_REGION"],
         "--secret-id", secret_id, "--query", "SecretString", "--output", "text"],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)

rds = secret(os.environ["RDS_SECRET_ARN"])
try:
    app = secret(os.environ["APP_SECRET_ID"])
except subprocess.CalledProcessError:
    sys.exit("App secret has no value yet. Put the backend env as JSON, then re-run c360-deploy:\n"
             "  aws secretsmanager put-secret-value --secret-id <app secret> --secret-string file://backend.json")

app["DATABASE_URL"] = (
    f"postgresql://{quote(rds['username'], safe='')}:{quote(rds['password'], safe='')}"
    f"@{rds['host']}:{rds['port']}/{rds['database']}?sslmode=require"
)
with open(sys.argv[1], "w") as fh:
    for key, value in app.items():
        if "\n" in str(value):
            sys.exit(f"Secret key {key} contains a newline")
        fh.write(f"{key}={value}\n")
os.chmod(sys.argv[1], 0o600)
PY

# ── 3. Build and (re)start ───────────────────────────────────────────────────
cd "${APP_DIR}/deploy"
docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null
echo "c360 deployed: $(git -C "${APP_DIR}" rev-parse --short HEAD)"
