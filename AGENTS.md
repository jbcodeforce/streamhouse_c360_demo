# Agent Guidelines and Architecture Decisions

This document outlines the architecture, decisions, security practices, and infrastructure standards applied across this repository.

---

## 1. Project Context

**Repository**: `streamhouse_c360_demo`  
**Purpose**: Customer 360 streaming data pipeline integrating operational databases (PostgreSQL, DB2) with event streaming, Change Data Capture (CDC), AI Agents integration, and modern lakehouse analytical sinks.

---

## 2. Infrastructure as Code (IaC) Layout

Terraform is organized under the [`IaC/`](IaC/) directory as **three independent root modules** (separate local state), each file-per-concern. This split lets the core Confluent Cloud stack runs locally with **no AWS credentials**; AWS and the managed connector are opt-in cost paths.

- [`IaC/ccloud/`](IaC/ccloud/) — **core Confluent Cloud stack (no AWS)**: environment, Kafka cluster, Flink compute pool, Schema Registry, service account + Kafka/SR API keys. Run with [`scripts/tf.sh`](scripts/tf.sh). Needs only `CONFLUENT_CLOUD_API_KEY/SECRET`.
- [`IaC/connector/`](IaC/connector/) — **managed Debezium Postgres CDC connector + AWS dependency**: reads the core stack's outputs from `../ccloud/terraform.tfstate` via `terraform_remote_state`, and the RDS credentials from AWS Secrets Manager. Run with [`scripts/tf_connector.sh`](scripts/tf_connector.sh) (needs AWS creds). Optional — in local mode the backend app writes Debezium-shaped events directly to `cdc.public.*` topics instead, or Debezium can run locally against a local Postgres (see section 3).
- [`IaC/AWS/`](IaC/AWS/) — **AWS stack**: PostgreSQL RDS 17 (CDC-ready), VPC/subnet lookups, security group (allowlists Confluent egress IPs), KMS, and the Secrets Manager secret consumed by `IaC/connector/`. Run with [`scripts/tf_aws.sh`](scripts/tf_aws.sh) (needs AWS creds + `CONFLUENT_CLOUD_API_KEY/SECRET` exported; the security group reads Confluent egress IPs). Files: `provider.tf`, `variables.tf`, `data.tf`, `aws.tf`, `outputs.tf`.

- [`IaC/EC2/`](IaC/EC2/) — **app host**: one Amazon Linux 2023 EC2 instance that builds and runs the backend and frontend containers with `docker compose` ([`deploy/`](deploy/), [`apps/backend/Dockerfile`](apps/backend/Dockerfile), [`apps/frontend/Dockerfile`](apps/frontend/Dockerfile)). Reads `IaC/AWS` state (VPC, RDS secret, KMS key). HTTP/SSH only from `allowed_cidr_blocks` (never `0.0.0.0/0`); backend env comes from a Secrets Manager secret at deploy time. Run with [`scripts/tf_ec2.sh`](scripts/tf_ec2.sh) (needs AWS creds). Container images use free UBI bases from `registry.access.redhat.com`. See [`IaC/EC2/README.md`](IaC/EC2/README.md).

**Apply order:** `IaC/ccloud` (always) → `IaC/AWS` + `IaC/connector` (only for the full CDC-over-AWS path) → `IaC/EC2` (optional, hosts the apps; needs `IaC/AWS`).

---

## 3. Local PostgreSQL and Debezium (no AWS)

Scripts under [`IaC/local/`](IaC/local/) run the CDC path entirely on the workstation with the **Apple Container CLI** (`container`): a PostgreSQL 17 container plus a Debezium (Kafka Connect) container that publishes Avro change events to Confluent Cloud. This replaces `IaC/connector/` + `IaC/AWS/` for local work. Full details: [`IaC/local/DEBEZIUM_SETUP.md`](IaC/local/DEBEZIUM_SETUP.md).

- [`start_local_pg_server.sh`](IaC/local/start_local_pg_server.sh): starts the `c360-postgres` container (`dbadmin` / `localdevonly`, db `c360db`, port 5432).
- [`create_debezium_topics.sh`](IaC/local/create_debezium_topics.sh): creates the Kafka Connect storage topics `my_connect_configs`, `my_connect_offsets`, `my_connect_status` via the Kafka REST API. Replication factor **3** is mandatory on Confluent Cloud. The REST endpoint is derived from `KAFKA_BOOTSTRAP_SERVERS`; idempotent.
- [`start_debezium.sh`](IaC/local/start_debezium.sh): the single entry point (`--reset`, `--stop`, `--logs`). It validates Postgres, ensures the topics exist, downloads the checksum-verified Confluent Avro converter into `~/.cache/c360-debezium`, starts the `c360-debezium` worker (REST API on `localhost:8083`), applies connector `postgres-cdc` with an idempotent `PUT /connectors/postgres-cdc/config`, and waits for `RUNNING`.

```bash
cd IaC/local
./start_local_pg_server.sh
# Start the backend once (or run apps/backend/bootstrap.py)
# so the tables and c360_cdc_publication exist.
./start_debezium.sh
```

Key behaviors to preserve:

- **Credentials** come from `apps/backend/.env` (gitignored): `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_API_KEY/SECRET`, `SCHEMA_REGISTRY_URL`, `SCHEMA_REGISTRY_API_KEY/SECRET`. Already-exported variables win over the file.
- **Connector config**: `pgoutput` plugin, publication `c360_cdc_publication` (owned by the backend bootstrap, `publication.autocreate.mode=disabled`), slot `debezium_slot`, tables `public.{accounts,customers,transactions}`, `topic.prefix=cdc` → `cdc.public.*`, Avro key/value converters against Schema Registry.
- **Worker env vars** must use the `CONNECT_` prefix (e.g. `CONNECT_*_STORAGE_REPLICATION_FACTOR=3`) or the image ignores them. SASL settings are needed for the worker, producer, admin and consumer clients.
- **Postgres is addressed by the container IP** (read from `container list`), not `localhost`, which inside the Debezium container is the container itself.
- **Do not create the slot with `test_decoding`** (as `configure_pg_cdc.sh` does): the connector requires `pgoutput`, and `start_debezium.sh` aborts with the drop command if a mismatched slot exists. `configure_pg_cdc.sh` also creates `debezium_pub` on a `cdc` schema that does not exist; it is only needed to turn on `wal_level=logical`, and `./scripts/run_dev.sh --cdc` still calls it.
- **The backend never produces `cdc.public.*`**: the Kafka producers and the `SINK` / `KAFKA_PRODUCE_ENABLED` / `CDC_CONNECTOR_ENABLED` settings were removed; all change events come from Debezium.
- `debezium-postgres.conf` is a legacy reference and is not used by the scripts.

---

## 4. Completed Infrastructure Components

### PostgreSQL RDS Instance (AWS West)

1. **Existing Network Integration**:
   - Reuses an existing VPC discovered dynamically via `data.aws_vpc.existing` (configurable by `vpc_id` or `vpc_name_tag`, or defaulting to the default VPC).
   - Reuses existing subnets via `data.aws_subnets.existing` or explicit `subnet_ids` list.
   - `aws_db_subnet_group` links the discovered subnets for RDS placement.

2. **Security & Cryptography**:
   - **KMS Encryption**: Dedicated Customer-Managed Key (`aws_kms_key`) with annual key rotation enabled for storage at rest and performance insights.
   - **Secrets Management**: Credentials automatically generated via `random_password` (24 chars) and written directly to AWS Secrets Manager (`aws_secretsmanager_secret`), eliminating plain-text secrets in git.
   - **Network Security**: Security Group restricting ingress on port 5432 strictly to specified CIDRs (Confluent Cloud NAT Egress IPs, workstation IP/32, and VPC CIDR). In-transit encryption (`rds.force_ssl = 1`) is mandatory.

3. **Database & CDC Readiness**:
   - Engine: PostgreSQL 17 (parameter group family `postgres17`).
   - Custom parameter group enforces TLS (`rds.force_ssl = 1`) and enables `rds.logical_replication = 1` to support real-time Change Data Capture (Debezium / Confluent Kafka Connect / Flink).
   - Automated backups (7-day retention) and CloudWatch log exports (`postgresql`, `upgrade`).

### Customer 360 Schema Bootstrap (backend-owned)

The backend is the single source of truth for the schema, the `c360_cdc_publication`
logical replication publication, and the seed data. On startup,
the FastAPI lifespan runs [`apps/backend/bootstrap.py`](apps/backend/bootstrap.py),
which, for `customers` → `accounts` → `transactions` (FK order):

- creates the table, indexes, and `updated_at` triggers (`CREATE ... IF NOT EXISTS`);
- adds the table to `c360_cdc_publication` (created if absent);
- seeds from the committed CSV in each service's `data/` directory, only if the table is empty.

Everything is idempotent, so it runs on every startup. To bootstrap **any** Postgres
(RDS included) without starting the API, run the same orchestration directly:

```bash
cd apps/backend
DATABASE_URL="postgresql://<user>:<pw>@<host>:5432/<db>?sslmode=require" \
  uv run python bootstrap.py
```

Two prerequisites stay outside the app: the RDS parameter group must set
`rds.logical_replication = 1` (see above), and the RDS secret must be supplied to the
backend as `DATABASE_URL`. The schema's field definitions live in each service's
`db_sink.py`; shared connection/transaction/seed mechanics live in
[`apps/backend/db.py`](apps/backend/db.py).

### Local Testing (scripts/)

Scripts for running services locally during development live under [`scripts`](scripts).

- [`scripts/local_start_pg.sh`](scripts/local_start_pg.sh): Starts a PostgreSQL 17 container via the **Apple Container CLI** (`container`) and, with `--seed`, runs the backend bootstrap (schema, `c360_cdc_publication`, seed data) against it.
- [`scripts/run_dev.sh`](scripts/run_dev.sh): runs the dev stack; `--cdc` configures local Postgres and starts Debezium via [`IaC/local/`](IaC/local/) (see section 3), `--no-debezium` skips the Debezium step.

```bash
# Start container only
./scripts/local_start_pg.sh

# Start + create schema/publication + seed data in one step
./scripts/local_start_pg.sh --seed

# Tear down when done
./scripts/local_start_pg.sh --stop

# Full dev stack with local Postgres CDC -> Confluent Cloud
./scripts/run_dev.sh --cdc
```

Environment overrides: `PG_PASSWORD` (default: `localdevonly`), `PG_PORT` (default: `5432`).

---

## 5. Best Practices for Future Agents & Contributors

When extending this repository, adhere to the following principles:

### A. Security & Compliance
- **No Hardcoded Credentials**: Never commit passwords, tokens, or API keys. Always use AWS Secrets Manager, HashiCorp Vault, or environment variables.
- **Principle of Least Privilege**: Ingress security group rules must target exact subnet CIDRs or security group references. Never bind databases or internal services to `0.0.0.0/0`.
- **Encryption by Default**: All persistent data stores (RDS, EBS, S3) must use KMS customer-managed keys (CMK) with `enable_key_rotation = true`.
- **Enforce TLS**: In-transit encryption (TLS 1.2+) is mandatory for all network communication and database clients.

### B. Terraform Standards
- **File Structure**:
  - `variables.tf`: Inputs and default configurations.
  - `data.tf`: External lookups and discovery (`aws_vpc`, `aws_subnets`, `aws_availability_zones`).
  - `outputs.tf`: Values intended for downstream consumers.
  - `aws.tf` / resource files: Pure resource definitions without inlining variables or outputs.
- **Resource Naming & Tagging**: Always tag resources with `Name`, `Environment`, and `Project` matching the standard `${var.project_name}-${var.environment}-*` convention.
- **Explicit Dependencies**: Use direct attribute references (e.g. `data.aws_vpc.existing.id`, `aws_kms_key.rds_key.arn`) to let Terraform build a deterministic DAG (Directed Acyclic Graph).

### C. CDC & Streaming Integration
- Any operational database added (PostgreSQL, DB2, MySQL) must be configured with CDC prerequisites:
  - Logical replication / WAL retention enabled.
  - User permissions granted for replication slots and publication creation.

### D. Python Tooling
- **All Python scripts in this repository use [uv](https://docs.astral.sh/uv/) as the package manager and runner.** Do not use `pip install`, `pipenv`, or `poetry`.
- Every Python script directory must contain a `pyproject.toml` (dependencies) and a committed `uv.lock` (pinned versions).
- Run scripts with `uv run python <script>.py` — uv handles the virtualenv automatically.
- Add new packages with `uv add <package>`; never edit `pyproject.toml` dependencies manually.
- Python version minimum: **3.11**. Always declare `requires-python = ">=3.11"` in `pyproject.toml`.

---

## 6. Statement Graph Page — recon notes (in design)

A new frontend page to visualize the deployed Flink statements that build a data
product as a DAG, with live status/metrics from the Confluent Cloud REST API.
Audience: solution engineers demoing "the art of the possible" (green-and-flowing,
then drill into a node for metrics). Relevant existing structure:

**Frontend** (`apps/frontend`): React 19 + Vite 8, `react-router-dom` 7,
`lucide-react` icons, plain CSS in `src/styles/index.css` (no CSS framework).
Pages in `src/pages/*`, routed in `src/App.tsx` under a shared `AppLayout`.
Static `Sidebar.tsx` nav. API via `src/api/client.ts` → `request<T>()` hitting
`VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`). No graph library yet.

**Backend** (`apps/backend`): FastAPI, routers per entity under `api/` mounted at
`/api/v1`. CORS allows `localhost:5173`. `config.py::Settings` already holds Kafka +
Schema Registry creds; no Confluent Flink/REST proxy yet. No metrics/statements route yet.

**Pipeline topology** (source of the graph's nodes/edges): dbt (shift-left) under
`pipelines/`, compiled to Flink SQL. Dependency DAG (`pipelines/target/manifest.json`,
`pipelines/models/deploy_manifest.json`):
- Sources (CDC topics): `cdc.public.customers`, `cdc.public.accounts`, `cdc.public.transactions`
- Models/statements: `src_customers`, `src_accounts`, `src_transactions` (each ← its CDC source),
  plus `src_dedup_*` variants. Deploy group `pipeline` in `deploy_manifest.json`.

**Confluent CLI/Flink tooling** present as skills: `flink-deploy`, `manifest`, `kafka`.
