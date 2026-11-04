# A Fast API Backend to simulate different microservices

The goal of this component is to offer REST APIs on customers, accounts, transactions resources. The backend, based on FastAPI, implements the following architecture.

![](../../docs/diagrams/backend.drawio.png)

Each component is isolated in term of code base so it can be packaged, if needed as microservice. 
 
The structure is the same for all compoents:

* REST API resource 
* Persist to PostgreSQL. Changes reach Kafka only through the Debezium CDC connector (`IaC/local/start_debezium.sh` locally, the managed connector on RDS); the backend never produces `cdc.public.*` events itself.

* CSV bootstrap for controlled data. On startup the backend auto-creates the schema and the `c360_cdc_publication`, then seeds each table from its CSV if empty.
* Centralise all environment-driven settings in one place so every module imports from `config` rather than calling `os.environ` directly. The dotenv file path is read from the `ENV_CONFIG_FILE` environment variable (default `.env`); real environment variables always take precedence over its contents.
* Define the canonical Pydantic schema for a Customer, matching the PostgreSQL table exactly (field names, types, optionality). This model is shared by the API request/response and database layers.
* Inventory pattern: the committed CSVs are loaded into typed models used to seed PostgreSQL.
* Leverage a thin orchestration layer (`service.py`) that delegates CRU operations to `db_sink.py`.
* Expose the Customers CRU endpoints as a FastAPI `APIRouter`. The router delegates all logic to `service.py` and handles HTTP status codes.
* Local postgres server for integration tests and demonstration
* The `main.py` wires the FastAPI app, includes routers, and runs startup lifecycle hooks (schema creation + CSV seeding).
    ```sh
    uv run uvicorn main:app --reload
    ```

* TheFastAPI backend is under `apps/backend/`
* This is a `uv` managed project

## Customers CRUD operations

Exposes a **Customers CRU REST API**. The seed file (`customers/data/customers.csv`) ships with 10 pre-populated customers. 

**Expected Outcomes:**
- `POST /customers` → 201 Created, returns `Customer`
- `GET /customers` → 200, returns `list[Customer]`
- `GET /customers/{customer_id}` → 200 or 404
- `PUT /customers/{customer_id}` → 200 or 404

## Accounts CRU operations

Exposes an **Accounts CRUD REST API** mirroring customers, stored in Postgres.

**Expected Outcomes:**
- `POST /accounts` → 201 Created, returns `Account` (409 on duplicate `account_number`)
- `GET /accounts` → 200, returns `list[Account]`
- `GET /accounts/{account_id}` → 200 or 404
- `PUT /accounts/{account_id}` → 200 or 404
- `DELETE /accounts/{account_id}` → 204 or 404

## Generating transactions (`POST /transactions/generate`)

Creates 200 transactions on **existing, ACTIVE accounts** (each with its owning `customer_id` and the account currency) and returns them (201). `409` if no active account exists.

Timestamps simulate a week of organic activity regardless of how fast the batch is produced: the first `transacted_at` is *now − 7 days* and each next transaction is *+15 minutes* (200 transactions span ~50 h). `posted_at` equals `transacted_at`.

Rows are inserted in a single DB transaction; the Debezium connector publishes them to `cdc.public.transactions`. The frontend Transactions page exposes this as the **Generate 200 transactions** button and then shows the result on `/transactions/generated`.


## Testing

1. Start the container
```sh
cd apps/backend
./start_local_pg_server.sh
```

2. Point the backend at it
```sh
cp .env.local .env
```

3. Start the API (auto-creates schema + seeds 10 customers on first boot)
```sh
uv run uvicorn main:app --reload
```

4. Access the REST API at [http://localhost:8000/docs](http://localhost:8000/docs) for the Swagger UI or http://localhost:8000/api/v1/customers

### Integration tests

```sh
uv run pytest -v tests/
```