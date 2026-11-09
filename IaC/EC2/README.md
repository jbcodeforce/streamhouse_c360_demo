# IaC/EC2 — C360 app host

One Amazon Linux 2023 EC2 instance that runs the backend (FastAPI) and frontend (nginx + SPA) with `docker compose`. Container images are built **on the instance** from the repo, using free UBI images from `registry.access.redhat.com` (no login or subscription).

```
browser ──HTTP :80──► nginx (frontend, :8080) ──/api/──► backend (FastAPI, :8000) ──► RDS / Confluent Cloud
                       only published port                compose network only
```

## What is created

| File | Resources |
|---|---|
| `ec2.tf` | Security group (80 and 22 from `allowed_cidr_blocks` only), Secrets Manager secret `c360-<env>-app-env`, IAM role (SSM + read the two secrets + `kms:Decrypt`), instance profile, EC2 instance (IMDSv2, KMS-encrypted gp3 root volume) |
| `data.tf` | `IaC/AWS` remote state, AL2023 AMI, public subnet lookup |
| `user_data.sh.tftpl` | Installs docker, git, and the pinned, checksum-verified compose and buildx plugins, installs `c360-deploy`, runs the first deploy |

Related files outside this directory:
- [`deploy/docker-compose.yml`](../../deploy/docker-compose.yml) and [`deploy/c360-deploy.sh`](../../deploy/c360-deploy.sh) (installed on the host as `/usr/local/bin/c360-deploy`)
- [`apps/backend/Dockerfile`](../../apps/backend/Dockerfile) and [`apps/frontend/Dockerfile`](../../apps/frontend/Dockerfile)
- [`scripts/tf_ec2.sh`](../../scripts/tf_ec2.sh) (wrapper)

The RDS security group from `IaC/AWS` already allows 5432 from the whole VPC CIDR, so no database rule is added here. The app host must be in that VPC.

## Prerequisites

1. `IaC/AWS` applied. This stack needs its `vpc_id`, `secrets_manager_secret_arn` and `kms_key_arn` outputs. `kms_key_arn` is new, so re-apply `IaC/AWS` once (`scripts/tf_aws.sh apply`) to add the output.
2. An existing EC2 key pair (`key_pair_name`).
3. A git repo URL reachable over HTTPS without credentials (`repo_url`).

## Apply

```bash
cd IaC/EC2
cp terraform.tfvars.example terraform.tfvars   # edit: key pair, your IP/32, repo_url
cd ../..
scripts/tf_ec2.sh init
scripts/tf_ec2.sh apply
```

## Provide the backend settings (once)

The first boot cannot finish until the app secret has a value. Terraform deliberately does not manage the value, so it never lands in state or git. Create a JSON object of the variables from [`apps/backend/.env.example`](../../apps/backend/.env.example) **except `DATABASE_URL`**, which is built at deploy time from the RDS secret:

```bash
cat > /tmp/backend.json <<'EOF'
{
  "KAFKA_BOOTSTRAP_SERVERS": "pkc-xxxxx.us-west-2.aws.confluent.cloud:9092",
  "KAFKA_API_KEY": "...",
  "KAFKA_API_SECRET": "...",
  "SCHEMA_REGISTRY_URL": "https://psrc-xxxxx.us-west-2.aws.confluent.cloud",
  "SCHEMA_REGISTRY_API_KEY": "...",
  "SCHEMA_REGISTRY_API_SECRET": "..."
}
EOF
aws secretsmanager put-secret-value \
  --secret-id "$(cd IaC/EC2 && terraform output -raw app_secret_arn)" \
  --secret-string file:///tmp/backend.json
shred -u /tmp/backend.json 2>/dev/null || rm -f /tmp/backend.json
```

Values must be single-line.

## Deploy / redeploy

```bash
aws ssm start-session --target "$(cd IaC/EC2 && terraform output -raw instance_id)"
# or: ssh -i <key.pem> ec2-user@<public_ip>
sudo c360-deploy          # pulls repo_ref, rewrites backend.env (mode 600), docker compose up -d --build
```

Open `terraform output app_url` from an allowed IP. Boot log: `/var/log/cloud-init-output.log`.

## Notes

- HTTP only (no TLS), limited to `allowed_cidr_blocks`. Put TLS in front before exposing this beyond a demo.
- `allowed_cidr_blocks` rejects `0.0.0.0/0` and `::/0`.
- The frontend is built with `VITE_API_BASE_URL=/api/v1`, so the browser calls the same origin and the hard-coded CORS origin in `apps/backend/main.py` is not involved.
- Building images on the instance needs about 4 GiB RAM (default `t3.medium`).
