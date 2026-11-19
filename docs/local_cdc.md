# Local CDC: PostgreSQL → Debezium → Confluent Cloud

Run the CDC path entirely on your workstation: a local PostgreSQL 17 container and a Debezium (Kafka Connect) container publish Avro change events to Confluent Cloud Kafka. This replaces the managed connector in `IaC/connector/` and the RDS instance in `IaC/AWS/`.

## Architecture

![](./diagrams/local/local_cdc.drawio.png)

## Prerequisites

- macOS with the Apple [`container`](https://github.com/apple/container) CLI.
- [`uv`](https://docs.astral.sh/uv/) (used by the backend bootstrap).
- A Confluent Cloud environment (see `IaC/ccloud/`).

## Getting Started

### 1. Set Confluent Cloud credentials

All variables live in `apps/backend/.env` (gitignored). Generate it from the Terraform outputs:

```sh
./scripts/set_env_from_tf.sh
```

Debezium needs `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_API_KEY`, `KAFKA_API_SECRET`, `SCHEMA_REGISTRY_URL`, `SCHEMA_REGISTRY_API_KEY` and `SCHEMA_REGISTRY_API_SECRET`. Variables already exported in your shell take precedence over the file.

### 2. Start the stack

```sh
# Start the Apple container runtime
container system start

cd IaC/local

# PostgreSQL 17 with wal_level=logical, plus schema, publication and seed data
./start_local_pg_server.sh --seed

# Debezium worker + connector (waits until the connector is RUNNING)
./start_debezium.sh
```

`--seed` runs `apps/backend/bootstrap.py`, which creates the tables, the `c360_cdc_publication` publication and the seed data. The Postgres container is already started with `wal_level=logical`, so no extra CDC configuration step is needed.

Or run both through the dev script: `./scripts/run_dev.sh --cdc`.

Verify the containers:

```sh
container ls
```

```text
ID              IMAGE                                  OS     ARCH   STATE    IP                CPUS  MEMORY   STARTED
c360-debezium   quay.io/debezium/connect:3.0.0.Final   linux  arm64  running  192.168.64.66/24  4     2048 MB  2026-11-10T18:10:56Z
c360-postgres   docker.io/library/postgres:17          linux  arm64  running  192.168.64.64/24  4     1024 MB  2026-11-10T17:58:24Z
```

#### Other platforms (docker compose, untested)

The Apple `container` CLI does not support `docker-compose.yml`. On other platforms, `IaC/local/` includes a compose file. It has **not been tested yet**.

```sh
cd IaC/local
docker compose --env-file ../../apps/backend/.env up -d --build

# Once Postgres is healthy: create tables, publication and seed data
(cd ../../apps/backend && \
  DATABASE_URL="postgresql://dbadmin:localdevonly@localhost:5432/c360db?sslmode=disable" \
  uv run python bootstrap.py)

docker compose --env-file ../../apps/backend/.env logs -f debezium-connector
```

### 3. Verify the pipeline

**Kafka topics.** Debezium captures the `public` schema tables listed below. In the Confluent Cloud console, check for the topics:

- `cdc.public.accounts`
- `cdc.public.cards`
- `cdc.public.customers`
- `cdc.public.transactions`

**Connector status:**

```sh
curl -s http://localhost:8083/connectors/postgres-cdc/status | jq
```

**PostgreSQL data.** Use any PostgreSQL client or IDE plugin (Bob, VS Code, Cursor) on `localhost:5432`:

<figure markdown='span'>
![](./images/postgresql-tables-vscode.png)
</figure>

### 4. Stop and reset

```sh
cd IaC/local

# Debezium
./start_debezium.sh --stop         # stop and remove the worker
./start_debezium.sh --reset        # recreate the worker (Kafka state kept)
./start_debezium.sh --full-reset   # also wipe Connect topics and drop the replication slot (forces a re-snapshot)

# PostgreSQL
./start_local_pg_server.sh --stop    # stop and remove the container
./start_local_pg_server.sh --reset   # fresh container (data is lost)
```

After resetting PostgreSQL, run `./start_debezium.sh --full-reset` so the replication slot and offsets match the new database.

## Configuration

### PostgreSQL

Set by `start_local_pg_server.sh` when starting the container:

| Setting | Value |
|---|---|
| `wal_level` | `logical` |
| `max_wal_senders` | `4` |
| `max_replication_slots` | `4` |
| Publication | `c360_cdc_publication` (created by the backend bootstrap) |
| Replication slot | `debezium_slot` (created by Debezium) |

Optional overrides (defaults shown):

```sh
export LOCAL_PG_USER=dbadmin
export LOCAL_PG_PASSWORD=localdevonly
export LOCAL_PG_DB=c360db
export PG_PORT=5432
```

### Debezium connector

`start_debezium.sh` is the single entry point. It checks Postgres, creates the Connect storage topics (`my_connect_configs`, `my_connect_offsets`, `my_connect_status`, replication factor 3), downloads the Confluent Avro converter, starts the `c360-debezium` worker (REST API on `localhost:8083`) and applies the `postgres-cdc` connector with an idempotent `PUT /connectors/postgres-cdc/config`.

| Setting | Value |
|---|---|
| Plugin | `pgoutput` |
| Publication | `c360_cdc_publication` (`publication.autocreate.mode=disabled`) |
| Slot | `debezium_slot` |
| Tables | `public.accounts`, `public.cards`, `public.customers`, `public.transactions` |
| Topic prefix | `cdc` → `cdc.public.<table>` |
| Format | Avro key and value, via Confluent Schema Registry |
| Snapshot | `snapshot.mode=initial` |
| Tombstones | `tombstones.on.delete=true` |
| Topic creation | 6 partitions, replication factor 3 |

The connector reaches Postgres through the container IP (read from `container list`), not `localhost`, which inside the Debezium container would be the container itself.

## Troubleshooting

### Debezium container won't start

```sh
(cd IaC/local && ./start_debezium.sh --logs)
```

Common causes:

- PostgreSQL is not running: `./start_local_pg_server.sh`.
- `wal_level` is not `logical` (container started elsewhere): recreate it with `./start_local_pg_server.sh --reset --seed`.
- Confluent Cloud or Schema Registry credentials are missing from `apps/backend/.env` and the shell.
- The publication does not exist: run the backend bootstrap (`./start_local_pg_server.sh --seed`).

### No messages in Confluent Cloud

1. Check that the replication slot exists:

   ```sh
   container exec c360-postgres psql -U dbadmin -d c360db -c "SELECT * FROM pg_replication_slots;"
   ```

2. Check that the publication covers the tables:

   ```sh
   container exec c360-postgres psql -U dbadmin -d c360db -c "SELECT * FROM pg_publication_tables WHERE pubname='c360_cdc_publication';"
   ```

3. Check the connector task state (see step 3).

### Replication slot already exists, or doesn't match

The slot is left over from a previous run, or was created with a different plugin. The connector requires `pgoutput`. Run `./start_debezium.sh --full-reset`, or drop it manually:

```sh
container exec c360-postgres psql -U dbadmin -d c360db -c \
  "SELECT pg_drop_replication_slot('debezium_slot');"
```
