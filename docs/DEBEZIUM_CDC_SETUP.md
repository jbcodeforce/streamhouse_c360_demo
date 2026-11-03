# Debezium CDC Setup: PostgreSQL → Confluent Cloud Kafka

This guide configures local PostgreSQL with Change Data Capture (CDC) via Debezium, streaming database changes to Confluent Cloud Kafka.

## Quick Start

### 1. Set Confluent Cloud Credentials

Add to `apps/backend/.env` (loaded via `ENV_CONFIG_FILE`):

```bash
export CONFLUENT_CLOUD_API_KEY=<your-api-key>
export CONFLUENT_CLOUD_API_SECRET=<your-api-secret>
export CONFLUENT_CLOUD_BOOTSTRAP_SERVER=pkc-v12gj.us-east-2.aws.confluent.cloud:9092
```

Or export them in your shell:

```bash
export CONFLUENT_CLOUD_API_KEY=<your-api-key>
export CONFLUENT_CLOUD_API_SECRET=<your-api-secret>
export CONFLUENT_CLOUD_BOOTSTRAP_SERVER=pkc-v12gj.us-east-2.aws.confluent.cloud:9092
```

### 2. Start Dev Stack with CDC

```bash
./scripts/run_dev.sh --cdc
```

This configuration matches the managed connector defined in `IaC/connector/connector.tf`.

This will:
1. Start local PostgreSQL (if not running)
2. Configure PostgreSQL for logical replication
3. Create replication slot and publication for `cdc.*` schema
4. Start Debezium server in a container
5. Start backend and frontend

### 3. Verify Pipeline

Once running, CDC captures tables in `cdc.public` schema. Check Confluent Cloud console for topics:
- `cdc-cdc.public.accounts`
- `cdc-cdc.public.customers`
- `cdc-cdc.public.transactions`

Insert or modify data in any `cdc.public.*` table to see CDC events flow to Confluent Cloud within seconds (AVRO format).

## Components

### Local PostgreSQL (Container)

- **Container**: `c360-postgres`
- **Image**: `postgres:17`
- **Port**: 5432
- **User**: `dbadmin`
- **Password**: `localdevonly` (configurable via `PG_PASSWORD`)
- **Database**: `c360db`

Start/stop:

```bash
# Start PostgreSQL
(cd IaC/local && ./start_local_pg_server.sh)

# Configure for CDC
(cd IaC/local && ./configure_pg_cdc.sh)

# Stop PostgreSQL
(cd IaC/local && ./start_local_pg_server.sh --stop)

# Reset (fresh start)
(cd IaC/local && ./start_local_pg_server.sh --reset)
```

### Debezium Server (Container)

- **Container**: `c360-debezium`
- **Image**: `quay.io/debezium/server:latest`
- **REST API**: `http://localhost:8083`
- **Connector Name**: `postgres-cdc`
- **Config File**: `IaC/local/debezium-postgres.conf` (matches managed connector)

The Debezium server:
- Runs logical replication against PostgreSQL
- Uses slot: `debezium_slot`
- Publishes to publication: `debezium_pub`
- Captures: `cdc.public.accounts`, `cdc.public.customers`, `cdc.public.transactions`
- Format: AVRO (with Schema Registry)
- Produces to Confluent Cloud Kafka

Start/stop:

```bash
# Start Debezium
(cd IaC/local && ./start_debezium_server.sh)

# View logs
(cd IaC/local && ./start_debezium_server.sh --logs)

# Stop Debezium
(cd IaC/local && ./start_debezium_server.sh --stop)

# Reset (fresh start)
(cd IaC/local && ./start_debezium_server.sh --reset)
```

### Confluent Cloud

**Kafka Cluster**:
- Cluster ID: `lkc-7v233w`
- Bootstrap: `pkc-v12gj.us-east-2.aws.confluent.cloud:443`

**Schema Registry**:
- URL: `https://psrc-13go8y7.us-west-2.aws.confluent.cloud`

Topics created:
- CDC source: `postgres-cdc.cdc.<table>` (raw Debezium envelope)
- Format: JSON with schema registry

## Configuration

### PostgreSQL CDC Settings

Set in `configure_pg_cdc.sh` via environment or container:

- **wal_level**: `logical` (enables CDC)
- **max_wal_senders**: 4 (concurrent replication connections)
- **max_replication_slots**: 4 (replication slot limit)
- **Replication slot**: `debezium_slot`
- **Publication**: `debezium_pub` (all tables in `cdc` schema)

### Debezium Connector Settings

Set in Debezium configuration (auto-generated):

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

## Troubleshooting

### Debezium container won't start

Check logs:

```bash
(cd IaC/local && ./start_debezium_server.sh --logs)
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

3. Check Debezium logs:
   ```bash
   (cd apps/backend && ./start_debezium_server.sh --logs)
   ```

### PostgreSQL connection refused

Check PostgreSQL container is running:

```bash
container ls | grep c360-postgres
```

If not running, start it:

```bash
(cd apps/backend && ./start_local_pg_server.sh)
```

### Replication slot already exists error

The slot exists from a previous run. Either reset PostgreSQL or drop it manually:

```bash
container exec c360-postgres psql -U postgres -c \
  "SELECT pg_drop_replication_slot('debezium_slot');"
```

## Flink Integration (Optional)

To use Flink to decode CDC events and materialize them to Iceberg/Delta tables in Confluent Cloud:

See the `confluent-cloud-cdc-tableflow` skill for a complete pipeline setup.

## Stopping Everything

Stop CDC stack in order:

```bash
# 1. Stop backend/frontend
# (Ctrl-C in the run_dev.sh terminal)

# 2. Stop Debezium
(cd IaC/local && ./start_debezium_server.sh --stop)

# 3. Stop PostgreSQL
(cd IaC/local && ./start_local_pg_server.sh --stop)
```

## Configuration

**Base connector config**: `IaC/local/debezium-postgres.conf`
- Matches managed connector in `IaC/connector/connector.tf`
- Captures: `cdc.public.accounts`, `cdc.public.customers`, `cdc.public.transactions`
- Format: AVRO (with Confluent Schema Registry)
- Topic prefix: `cdc`

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
