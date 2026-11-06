#!/usr/bin/env bash
#
# Run Terraform in IaC/EC2 — the app host (EC2 instance, security group, IAM,
# Secrets Manager secret for the backend env). Reads IaC/AWS state, so apply
# IaC/AWS first (scripts/tf_aws.sh).
#
# Usage:
#   scripts/tf_ec2.sh init
#   scripts/tf_ec2.sh plan
#   scripts/tf_ec2.sh apply
#   AWS_PROFILE=nonprod-administrator-829250931565 scripts/tf_ec2.sh plan
#
# Prerequisites:
#   - An AWS profile that resolves to the same account as IaC/AWS (defaults to
#     the `default` profile; override with AWS_PROFILE).
#   - IaC/EC2/terraform.tfvars (copy terraform.tfvars.example).
#
# Why this wrapper exists: the AWS provider's Go SDK does not reliably resolve an
# SSO profile via AWS_PROFILE, so we refresh the SSO token if needed and export
# the complete temporary credential triple (see tf_aws.sh for details).
set -euo pipefail

AWS_PROFILE_NAME="${AWS_PROFILE:-default}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EC2_DIR="$(cd "${SCRIPT_DIR}/../IaC/EC2" && pwd)"

if ! aws sts get-caller-identity --profile "${AWS_PROFILE_NAME}" >/dev/null 2>&1; then
  echo "AWS SSO token for profile '${AWS_PROFILE_NAME}' is missing or expired; logging in..." >&2
  aws sso login --profile "${AWS_PROFILE_NAME}"
fi
eval "$(aws configure export-credentials --profile "${AWS_PROFILE_NAME}" --format env)"

# Guard against a profile that resolves to the WRONG AWS account (same default as
# tf_aws.sh). Set EXPECTED_AWS_ACCOUNT_ID= (empty) to skip.
EXPECTED_AWS_ACCOUNT_ID="${EXPECTED_AWS_ACCOUNT_ID-829250931565}"
if [[ -n "${EXPECTED_AWS_ACCOUNT_ID}" ]]; then
  ACTUAL_AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)"
  if [[ "${ACTUAL_AWS_ACCOUNT_ID}" != "${EXPECTED_AWS_ACCOUNT_ID}" ]]; then
    echo "ERROR: AWS credentials resolve to account '${ACTUAL_AWS_ACCOUNT_ID:-<unknown>}', expected '${EXPECTED_AWS_ACCOUNT_ID}'." >&2
    echo "       Profile '${AWS_PROFILE_NAME}' points at the wrong account." >&2
    exit 1
  fi
fi

cd "${EC2_DIR}"
exec terraform "$@"
