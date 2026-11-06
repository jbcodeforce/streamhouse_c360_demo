# EC2 Deployment Plan (Terraform + Dockerfiles)

## Overview

Package `apps/backend` (FastAPI, uv) and `apps/frontend` (React/Vite) as container images and run them on a single EC2 instance provisioned by a new Terraform root module `IaC/EC2/`.

Decisions (confirmed with user):
- New independent root module `IaC/EC2/` (own local state), same file-per-concern layout as `IaC/AWS/`. It reads `IaC/AWS` state via `terraform_remote_state` for VPC, subnets, RDS security group, KMS key, and the RDS secret ARN.
- Host OS: Amazon Linux 2023 (free). Container base images: free UBI images from `registry.access.redhat.com` (no login or subscription), as required by `security.md`. Non-root `USER`, minimal images.
- Access: HTTP (80) and SSH (22) only from a workstation `/32` variable. No `0.0.0.0/0` ingress. SSM Session Manager is also enabled via the instance role. SSH needs an existing EC2 key pair name variable.
- App delivery: images are built **on the instance** (git clone or rsync, then `docker compose build`) from `user_data`. No ECR.
- Runtime: `docker compose` with two services: `frontend` (nginx serving the static build and proxying `/api` to the backend) and `backend` (uvicorn). Only nginx is published on the host. The backend is reachable only on the compose network.
- The frontend is built with `VITE_API_BASE_URL=/api/v1` (relative), so the hard-coded CORS origin in `apps/backend/main.py` (`http://localhost:5173`) does not need changing.
- Secrets: the RDS DSN comes from the existing Secrets Manager secret. Kafka and Schema Registry credentials come from a new Secrets Manager secret (KMS-encrypted) holding the backend env values. Both are fetched at boot via the instance role into a root-only env file. Nothing is committed or placed in `user_data` in clear text.
- The RDS security group gets one ingress rule (5432) from the EC2 SG, created in `IaC/EC2` as a separate `aws_vpc_security_group_ingress_rule`. This avoids a dependency cycle and edits to `IaC/AWS`.

## Sub-Tasks

### 1. Backend Dockerfile
- **Intent**: Reproducible image for the FastAPI backend.
- **Expected Outcomes**: `docker build apps/backend` produces a non-root image that starts uvicorn on port 8000. `GET /health` returns ok when env vars are supplied.
- **Todo List**:
  1. Create `apps/backend/Dockerfile`. Use a UBI python minimal base, install deps with `uv sync --frozen` from `pyproject.toml` and `uv.lock`, and run `uvicorn main:app` without `--reload`.
  2. Bind inside the container to the container interface only for the compose network. Do not publish the port on the host.
  3. Add `apps/backend/.dockerignore` excluding `.env*`, `.venv`, `__pycache__`, and tests.
  4. Add a container healthcheck against `/health`.
- **Relevant Context**: `apps/backend/pyproject.toml` (Python >=3.11), `apps/backend/main.py` (lifespan runs `bootstrap.init_and_seed()` and needs a reachable `DATABASE_URL`), `apps/backend/config.py` (`Settings`, env-driven), `scripts/run_dev.sh` (dev command). `psycopg2-binary` and `confluent-kafka` may need runtime libs on UBI, so verify on build.
- **Status**: `[x] done`

### 2. Frontend Dockerfile and nginx config
- **Intent**: Static build served by nginx, with `/api` reverse-proxied to the backend.
- **Expected Outcomes**: `docker build` with a build arg `VITE_API_BASE_URL` (default `/api/v1`) yields an unprivileged nginx image on a non-privileged internal port that serves the SPA (history fallback) and proxies `/api/` to `backend:8000`.
- **Todo List**:
  1. Create `apps/frontend/Dockerfile`: multi-stage, UBI Node build stage (`npm ci`, `npm run build`), then a UBI nginx runtime stage with non-root user.
  2. Add `apps/frontend/nginx.conf` with SPA fallback, `/api/` proxy, and timeouts.
  3. Add `apps/frontend/.dockerignore` excluding `node_modules`, `dist`, and `.env*`.
- **Relevant Context**: `apps/frontend/package.json` (build is `tsc -b && vite build`), `apps/frontend/.env.example` (`VITE_API_BASE_URL` is build-time), `apps/frontend/src/api/client.ts` (`request<T>()` uses `VITE_API_BASE_URL`).
- **Status**: `[x] done`

### 3. Compose file and EC2 bootstrap script
- **Intent**: Single definition of how both containers run on the host.
- **Expected Outcomes**: `docker compose up -d --build` on the instance starts both services. Only host port 80 is published. The backend gets an `env_file` generated at boot.
- **Todo List**:
  1. Create a `deploy/` directory (or `IaC/EC2/files/`) containing `docker-compose.yml`. Use `restart: unless-stopped`, `read_only` root filesystem where possible, and `cap_drop: [ALL]`.
  2. Create a boot script (rendered by Terraform `templatefile` into `user_data`) that does the following:
     - Installs docker and the compose plugin on AL2023.
     - Clones the repo from a `repo_url` and `repo_ref` variable.
     - Fetches the two Secrets Manager secrets with the instance role and writes `apps/backend/.env` with mode 600.
     - Runs compose.
  3. Make the script idempotent so it can be re-run through SSM or SSH to redeploy.
- **Relevant Context**: `apps/backend/.env.example` (variable names to place in the new secret), `AGENTS.md` section 4 (`DATABASE_URL` format with `sslmode=require`).
- **Status**: `[x] done`

### 4. Terraform module `IaC/EC2/`
- **Intent**: Provision the instance and its supporting resources following repo standards.
- **Expected Outcomes**: `terraform plan` shows the EC2 instance, security group, IAM role and profile, Secrets Manager secret, and the RDS SG ingress rule. After apply, the app is reachable at `http://<public-ip>/` from the allowed IP only.
- **Todo List**:
  1. Create `provider.tf` (AWS provider `~>5.0`, same Terraform constraint as `IaC/AWS`) and `variables.tf`. Variables: `project_name`, `environment`, `aws_region_primary`, `instance_type`, `key_pair_name`, `allowed_cidr_blocks` (workstation /32, validated to reject `0.0.0.0/0`), `repo_url`, `repo_ref`, `root_volume_size`, and `app_secret_name`.
  2. Create `data.tf`: `terraform_remote_state` on `../AWS/terraform.tfstate`, latest AL2023 arm64/x86 AMI via SSM parameter or `aws_ami`, and subnet selection (public subnet, public IP).
  3. Create `ec2.tf` (resources only):
     - Security group: 80 and 22 from `allowed_cidr_blocks`, egress open for package, GitHub, and Confluent access.
     - IAM role and instance profile with `AmazonSSMManagedInstanceCore` plus a least-privilege policy for `secretsmanager:GetSecretValue` on the two secrets and `kms:Decrypt` on the KMS key.
     - Instance with IMDSv2 required, root EBS encrypted with the existing KMS CMK, and tags `Name`, `Environment`, `Project`.
     - `aws_secretsmanager_secret` for backend env values (value supplied out of band, not in git).
     - `aws_vpc_security_group_ingress_rule` on the RDS SG from the EC2 SG, port 5432.
  4. Create `outputs.tf`: instance id, public IP, app URL, SSM connect hint.
  5. Add `scripts/tf_ec2.sh` modeled on `scripts/tf_aws.sh` (AWS credential and account validation).
  6. Expose any missing outputs from `IaC/AWS/outputs.tf` that the remote state needs, such as the KMS key ARN. Current outputs already include `vpc_id`, `db_security_group_id`, and `secrets_manager_secret_arn`.
  7. Add `IaC/EC2/.gitignore` for tfstate and tfvars, and a `terraform.tfvars.example`.
- **Relevant Context**: `IaC/AWS/{provider,variables,data,aws,outputs}.tf`, `scripts/tf_aws.sh`, `IaC/connector/` (remote state pattern), and `AGENTS.md` section 5B (Terraform standards).
- **Status**: `[x] done`

### 5. Docs and validation
- **Intent**: Make the new path discoverable and verified.
- **Expected Outcomes**: AGENTS.md and the README describe the apply order and the run steps. All checks pass.
- **Todo List**:
  1. Update `AGENTS.md` section 2 (IaC layout and apply order) and add a short `IaC/EC2/README.md` covering prerequisites, the secret payload, and redeploy steps.
  2. Run `terraform fmt -check` and `terraform validate` in `IaC/EC2`.
  3. Run `docker build` for both images if a container engine is available (Apple `container` CLI or docker). Report if not.
  4. Confirm no secrets are in the diff.
- **Relevant Context**: `AGENTS.md`, `README.md`, `docs/`.
- **Status**: `[x] done`

## Open Items / Risks
- Exact UBI image tags (Python, Node, nginx) need to be confirmed against `registry.access.redhat.com` at implementation time.
- Cloning a private repo from the instance needs a deploy token. This plan assumes `repo_url` is reachable. Otherwise use rsync over SSH or SSM.
- HTTP only (no TLS), restricted to your /32. This is a demo trade-off against the TLS rule in `security.md`. Adding TLS on a domain is a possible follow-up.
