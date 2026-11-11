# Debezium CDC Setup: PostgreSQL → Confluent Cloud Kafka

This guide configures local PostgreSQL with Change Data Capture (CDC) via Debezium, streaming database changes to Confluent Cloud Kafka.

## Architecture


![](./diagrams/local/local_cdc.drawio.png)


## Getting Started
### 1. Set Confluent Cloud Credentials

All the environment variables need to be defined in `apps/backend/.env`, which can be jumpstarted from the terraform output, via the command:

```sh
./scripts/set_env_from_tf.sh
```

### 2. Start Dev Stack with CDC

The following commands work with MacOS `container` cli. 

* Start the Apple container runtime:
   ```sh
   container system start 
   ```

* Start Postgresql
   ```sh
   cd IaC/local
    ./start_local_pg_server.sh
   ```
* Configure PostgreSQL for logical replication
   ```sh
   cd IaC/local
   ./configure_pg_cdc.sh
   ```

* Start the Connector
   ```bash
   cd IaC/local
   ./start_debezium.sh
   # View logs
   ./start_debezium.sh --logs
   ```

   This configuration matches the managed connector defined in `IaC/connector/connector.tf`.

* Verify running containers:
   ```sh
   container ls
   ```

   you should get:

   ```sh
   ID             IMAGE                                                OS     ARCH   STATE    IP                CPUS  MEMORY   STARTED
   c360-debezium  quay.io/debezium/connect:3.0.0.Final                 linux  arm64  running  192.168.64.66/24  4     2048 MB  2026-11-10T18:10:56Z
   c360-postgres  docker.io/library/postgres:17                        linux  arm64  running  192.168.64.64/24  4     1024 MB  2026-11-10T17:58:24Z
   ```


* Apple's native container CLI does not natively support docker-compose.yml files. For other platform the IaC/local folder includes a docker-compose file. NOT TESTED YET
   ```sh
   cd IaC/local
   docker compose --env-file ../../apps/backend/.env up -d --build
   # once Postgres is healthy: create tables, the publication and seed data
   (cd ../../apps/backend && DATABASE_URL="postgresql://dbadmin:localdevonly@localhost:5432/c360db?sslmode=disable" uv run python bootstrap.py)
   docker compose --env-file ../../apps/backend/.env logs -f debezium-connector
   ```

### 3.1 Verify Pipeline

Once running, CDC captures tables in `public` schema. Check Confluent Cloud console for topics:

- `cdc.public.accounts`
- `cdc.public.customers`
- `cdc.public.transactions`
- `cdc.public.cards`

### 3.2 Verify Data in Postgresql

Bob, VScode, Cursor have postgresql plugin to access local server.

<figure markdown='span'>
![](./images/postgresql-tables-vscode.png)
</figure>

### 4. Stopping Everything

* Debeziun
   ```bash
   # Stop Debezium
   (cd IaC/local && ./start_debezium.sh --stop)

   # Reset (fresh start)
   (cd IaC/local && ./start_debezium.sh --reset)
   ```

* Postgreql Server
   ```bash
   # Stop PostgreSQL
   (cd IaC/local && ./start_local_pg_server.sh --stop)

   # Reset (fresh start)
   (cd IaC/local && ./start_local_pg_server.sh --reset)
   ```


## Configuration

### PostgreSQL CDC Settings

Set in `configure_pg_cdc.sh` via environment or container:

- **wal_level**: `logical` (enables CDC)
- **max_wal_senders**: 4 (concurrent replication connections)
- **max_replication_slots**: 4 (replication slot limit)
- **Replication slot**: `debezium_slot`
- **Publication**: `debezium_pub` (all tables in `cdc` schema)

### Debezium Connector Settings

**Base connector config**: `IaC/local/debezium-postgres.conf`

- Matches managed connector in `IaC/connector/connector.tf`
- Captures: `cdc.public.accounts`, `cdc.public.customers`, `cdc.public.transactions`
- Format: AVRO (with Confluent Schema Registry)
- Topic prefix: `cdc`

```
# Database connection
database.hostname=localhost
database.port=5432
database.user=dbadmin
database.password=localdevonly
database.dbname=c360db

# Replication
plugin.name=pgoutput
database.publication.name=debezium_pub
database.slot.name=debezium_slot

# Table selection
table.include.list=cdc\.\*

# Kafka output
producer.bootstrap.servers=pkc-v12gj.us-east-2.aws.confluent.cloud:9092
producer.security.protocol=SASL_SSL
producer.sasl.mechanism=PLAIN

# CDC options
snapshot.mode=initial
decimal.handling.mode=string
tombstones.on.delete=true
```

**Runtime credentials injection**: Confluent Cloud credentials are injected from environment into the runtime config:

```bash
# Required for Debezium to connect to Confluent Cloud
export CONFLUENT_CLOUD_API_KEY=<key>
export CONFLUENT_CLOUD_API_SECRET=<secret>
export CONFLUENT_CLOUD_BOOTSTRAP_SERVER=pkc-v12gj.us-east-2.aws.confluent.cloud:9092
```

Add these to `apps/backend/.env` (via `ENV_CONFIG_FILE`) or export in your shell before running `./scripts/run_dev.sh --cdc`.

**Optional PostgreSQL overrides** (defaults shown):

```bash
export LOCAL_PG_USER=dbadmin
export LOCAL_PG_PASSWORD=localdevonly
export LOCAL_PG_HOST=localhost
export LOCAL_PG_PORT=5432
export LOCAL_PG_DB=c360db
```


## Troubleshooting

### Debezium container won't start

Check logs:

```bash
(cd IaC/local && ./start_debezium.sh --logs)
```

Common issues:
- PostgreSQL not running: start with `./start_local_pg_server.sh`
- PostgreSQL not configured for CDC: run `./configure_pg_cdc.sh`
- Confluent Cloud credentials missing: add to `apps/backend/.env` or export `CONFLUENT_CLOUD_*` vars
- Base config file missing: ensure `IaC/local/debezium-postgres.conf` exists

### No messages appearing in Confluent Cloud

1. Verify PostgreSQL replication slot exists:
   ```bash
   container exec c360-postgres psql -U dbadmin -d c360db -c "SELECT * FROM pg_replication_slots;"
   ```

2. Verify publication captures tables in `cdc` schema:
   ```bash
   container exec c360-postgres psql -U dbadmin -d c360db -c "SELECT * FROM pg_publication_tables WHERE pubname='debezium_pub';"
   ```

### Replication slot already exists error

The slot exists from a previous run. Either reset PostgreSQL or drop it manually:

```bash
container exec c360-postgres psql -U postgres -c \
  "SELECT pg_drop_replication_slot('debezium_slot');"
```
