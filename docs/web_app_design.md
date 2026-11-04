# Web App and Backend Design

This note is to explain the backend design and implementation, for code maintenance and also explaining some integration to Confluent Cloud Streamhouse capabilities

## Requirements addressed
 
* [x] Web App to present customers page and be able to add new customer, read the detail of one customer, update one, or delete one
* [x] Pages for accounts CRUD operations
* [x] Pages for transactions CR operations
* [x] Local persistence with Postgresql database running in container
* [x] Change events published to Kafka by Debezium CDC (no backend Kafka producer)
* [x] TDD for backend and frontend
* [x] Run snapshot queries from UI to backend to Confluent cloud on top of fact tables
* [x] Execute lightning query from a backend and display result to Frontend
* [x] Chat interface to demonstrate querying business data using Real-time context engine.

## Design

The solution architecture looks like in the figure below:

![](./diagrams/stream-cut1-local-arch.drawio.png)

The frontend is a classic single-page app over a REST backend.

![](./diagrams/web_app_flow.drawio.png)

The backend is organized in different layers to facilitate testing and adopting clear separation of concern. The structure mock a microservice implementation, which means it will be easy to separate the customer, account, transactions, analytics and chat into separate code repository and package them as 12-factors application.

### Frontend ↔ backend integration

The frontend (`apps/frontend`, React 19 + Vite + React Router) never calls `fetch` directly from a page. It is layered so the HTTP concern lives in one place:

* `src/config.ts` — resolves the backend base URL once: `VITE_API_BASE_URL ?? http://localhost:8000/api/v1`.
* `src/api/client.ts` — a thin `request<T>()` wrapper around `fetch` that sets JSON headers, unwraps `204 No Content`, and turns non-2xx responses into a typed `ApiError` (reading FastAPI's `{ "detail": ... }` body).
* `src/api/{customers,accounts,transactions,config}.ts` — one module per domain, exposing typed CRUD functions (`listAccounts`, `getAccount`, `createAccount`, …) that map 1:1 to the REST endpoints.
* `src/types/*` — TypeScript interfaces mirroring the backend Pydantic models, so the request/response contract is checked at compile time.
* `src/pages/*` and `src/components/*` — views call only the `api/` functions; they never know the base URL or status-code handling.

On the backend side, `main.py` mounts every domain router under `/api/v1` and enables CORS for the Vite dev origin (`http://localhost:5173`). The browser's
`VITE_API_BASE_URL` and the backend's CORS allow-list are the two ends of the same contract.

### Backend design pattern (models · DAO · producer · inventory)

Each domain — **customers**, **accounts**, **transactions**, **analytics**, **chat**, **data lineage** — is a similar vertical slice of small modules. Routing and HTTP stay thin; persistence and seeding are each isolated behind their own module:

| Layer | Module | Responsibility |
|-------|--------|----------------|
| **API** | `api/<domain>_resource.py` | FastAPI router. Validates input via the models, maps results/`404`/`409` to HTTP. No business logic. |
| **Service** | `<domain>/service.py` | Dispatch/orchestration. Delegates to the DAO. Postgres is the source of truth; Debezium publishes the changes to Kafka. |
| **Models** | `<domain>/models.py` | Pydantic `*Create` / `*Update` / full models. The single schema contract shared by the API, the DAO, and (mirrored) the frontend types. |
| **DAO** | `<domain>/db_sink.py` | Data-access object: the domain's PostgreSQL DDL, column list, row↔model mapping, and CRUD — built on the shared pool in `db.py`. |
| **Inventory** | `<domain>/inventory.py` | CSV-backed seed store. Loads the committed seed CSV into typed models used to seed PostgreSQL. |

Cross-cutting modules keep the slices DRY:

* `db.py` — one lazily-created connection pool, a `cursor()` context manager (commit/rollback/return-to-pool), and reusable `init_schema` / `seed_if_empty`
  / CDC-publication helpers. Each `db_sink` supplies only its own DDL and mapping; the connection and transaction mechanics are written once here.
* `bootstrap.py` — on startup (`main.py` lifespan), creates all tables + the `c360_cdc_publication`, then seeds **customers → accounts →
  transactions** in FK order, each table only if empty (idempotent).
* `config.py` — environment-derived `Settings` (`DATABASE_URL`, Kafka/SR credentials, topic names).

**Who owns Kafka.** Debezium (local container or the managed connector on RDS) is the only producer of the `cdc.public.*` topics; the backend has no Kafka producer for these entities.

A new domain is added by copying the slice, registering its router in `main.py`, and adding its `init_db` + `seed_from_csv` to `bootstrap.py`.

## Execute during development


* Start the database server
    ```sh
    cd apps/backend
    ./start_local_pg_server.sh
    ```

* Start the backend
    ```sh
    cd app/backend
    uv run python -m uvicorn main:app --reload 
    ```

    Access to REST API: [http://localhost:8000/docs](http://localhost:8000/docs)


* Start the user interface
    ```sh
    cd apps/frontend
    npm run dev
    ```

    Access to the webapp: [http://localhost:5173/](http://localhost:5173/)
    
## Database schema

The database has three main tables:

* Accounts:
    ```sql
        CREATE TABLE IF NOT EXISTS accounts (
        account_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        customer_id     UUID            NOT NULL REFERENCES customers(customer_id),
        account_number  VARCHAR(20)     NOT NULL UNIQUE,
        account_type    VARCHAR(30)     NOT NULL,  -- 'CHECKING', 'SAVINGS', 'CREDIT', 'LOAN'
        currency        CHAR(3)         NOT NULL DEFAULT 'USD',
        balance         NUMERIC(18, 2)  NOT NULL DEFAULT 0.00,
        credit_limit    NUMERIC(18, 2),            -- populated for CREDIT / LOAN accounts
        opened_date     DATE            NOT NULL DEFAULT CURRENT_DATE,
        closed_date     DATE,
        status          VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    )
    ```

* Customers
    ```sql
        CREATE TABLE IF NOT EXISTS customers (
        customer_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        first_name      VARCHAR(100)    NOT NULL,
        last_name       VARCHAR(100)    NOT NULL,
        email           VARCHAR(255)    NOT NULL UNIQUE,
        phone           VARCHAR(30),
        date_of_birth   TIMESTAMPTZ,
        gender          VARCHAR(20),
        address_line1   VARCHAR(255),
        address_line2   VARCHAR(255),
        city            VARCHAR(100),
        state           VARCHAR(100),
        postal_code     VARCHAR(20),
        country         VARCHAR(60)     NOT NULL DEFAULT 'US',
        customer_since  DATE            NOT NULL DEFAULT CURRENT_DATE,
        segment         VARCHAR(50),    -- e.g. 'RETAIL', 'SMB', 'ENTERPRISE'
        status          VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    )
    ```
    
* Transactions:
    ```sql
        CREATE TABLE IF NOT EXISTS transactions (
        transaction_id   UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
        account_id       UUID           NOT NULL REFERENCES accounts(account_id),
        customer_id      UUID           NOT NULL REFERENCES customers(customer_id),
        transaction_type VARCHAR(30)    NOT NULL,  -- 'DEBIT', 'CREDIT', 'TRANSFER', 'FEE', 'INTEREST'
        amount           NUMERIC(18, 2) NOT NULL,
        currency         CHAR(3)        NOT NULL DEFAULT 'USD',
        description      VARCHAR(500),
        merchant_name    VARCHAR(200),
        merchant_category VARCHAR(100),
        channel          VARCHAR(50),   -- 'ONLINE', 'ATM', 'POS', 'MOBILE', 'BRANCH'
        status           VARCHAR(20)    NOT NULL DEFAULT 'COMPLETED',
        transacted_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
        posted_at        TIMESTAMPTZ,
        created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW()
    )
    ```

## Query Customer Profile Facts

To query the customer profiles directly from Kafka, there are multiple different capabilities to use. Using SQL as an interface, and Streamhouse architecture, it is possible to leverage Flink snapshot query with the Confluent Cloud REST API for flink statement, or using the new Confluent lightning query via Real-Time Contect Engine.

### Analytics Dashboard — CRM Data Products

The C360 analytics dashboard (KPI tiles and distribution charts) does not pull every customer row and aggregate in the backend. The aggregates are materialized in Flink as a dedicated **CRM analytic data product** — five small tables built from `fct_c360_profile`:

| Table | Grain | Feeds in the dashboard |
|---|---|---|
| `fct_crm_summary` | one global row (`qscope='ALL'`) | KPI totals, averages, data-quality rollup |
| `fct_crm_by_segment` | per customer segment | segment counts + balance-by-segment |
| `fct_crm_by_generation` | per generation segment | generation counts |
| `fct_crm_by_gender` | per gender | gender counts |
| `fct_crm_by_country` | per country | country counts (top-8 + "Other") |

In live mode the backend (`analytics/crm_provider.py`) runs five trivial `SELECT *` **snapshot queries** — one per table — concurrently through the `confluent-sql` DB-API driver, 

![](./diagrams/snapshot_q_crm.drawio.png)

and `analytics/crm_aggregate.py` folds the pre-aggregated rows into the dashboard payload (`DataAnalytics`). Only the summary rows cross the wire; the aggregation stays in Flink. 

![](./images/fct_c360_profile_db.png)

* code involved:

  * [api/analytics_resource.py](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/api/analytics_resource.py)
  * [analytics/service.py](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/analytics/service.py)
  * [backend/analytics/providers.py](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/analytics/providers.py)
  * [analytics/crm_aggregate.py](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/analytics/crm_aggregate.py) to build aggregates for dashboard

### Snapshot Query

The frontend exposes a widget to query customer profile given his/her name. Once clicking on `Search` the front end first goes to load customer record from the database via the customer service and resources and the get the profile by running a Flink Snapshot query to get the data out of the fact c360 profile topic/table:

![](./images/snap_query_carter.png)

The process flow looks like:

![](./diagrams/snapshot_q_app_flow.drawio.png)

### Lightning Query Integration

The Frontend also exposes a widget to get a customer c360 profile given his/her last name

![](./images/LT_execution_carter.png)

This time the application logic flow leverages a client that use the REST API of lightning table:

![](./diagrams/LT_app_flow.drawio.png)

(The customer record is loaded from the database.)

### Real-Time Context Engine

This time the 'Assistant' user interface is to emulate an agent to call the [Confluent real-time context engine](https://docs.confluent.io/cloud/current/ai/real-time-context-engine/overview.html) to get real-time customer 360 profile data. 

![](./images/querying_with_chat_rtce.png)

In a developer centric demonstration, we will use an harness like Claude Code, codex, pi.dev... Here we want to simulate a business user who wants to get business data directly from Kafka.

* The frontend exposes a chat interface [/pages/ChatPage.tsx](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/frontend/src/pages/ChatPage.tsx) with a sendChatMessage(text, history) javascript method to reach the backend via a HTTP POST to `/chat`
* The backend resource [api/chat_resource.py](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/api/chat_resource.py) export an async function, which delegates to the service layer
  ```python
  @router.post("", response_model=ChatResponse, status_code=200)
  async def post_chat(request: ChatRequest) -> ChatResponse:
    return await service.get_reply(request)
  ```

* The [service](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/chat/service.py) manages the support to `stub` mode to return canned text or `live` mode to run the Agno agent against the local LLM + RTCE context-engine MCP server. 
* [Agno agent]((https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/chat/agent.py) ) wires a local OpenAI-compatible LLM (an MLX server) to the Confluent Real-Time Context Engine context-engine MCP server. 
  ```python
    model, server_params = _build_model_and_params()
    async with MCPTools(
        server_params=server_params,
        transport="streamable-http",
        timeout_seconds=_MCP_TIMEOUT_SECONDS,
    ) as tools:
        agent = Agent(model=model, tools=[tools], instructions=_INSTRUCTIONS, markdown=False)
        result = await agent.arun(input=prompt)
    return (result.content or "").strip()
  ```

The MCP server URL is derived from the Confluent (`config.settings.rtce_mcp_url()`). Auth is HTTP Basic with the org-wide GLOBAL key/secret. [Agno](https://docs.agno.com/tools/mcp/overview) SDK offers a set of constructs to simplify the definition of agent with prompt, tools, persistence...

It is interresting to see that a MCP ClientSession is stateful and single-session over streamable-HTTP. So the implementation uses a session, initiated from the frontend, and maintained until the user reset it. The session_id is a cache key + agno session id. Frontend generates a UUID on first submit, displays it, sends it every turn. A `Reset` button closes the server-side connection and starts a new UUID. Conversation continuity stays frontend-driven, the history is sent from the UI and injected into the prompt. The cache is purely connection/agent reuse for latency. Session_id also tags the agno run for visibility. The connection is lazily created on first message of a session (preserves graceful degradation), reuse until Reset. The idle-TTL is set to 30 min and a max-sessions cap evict stale ones, app shutdown closes all. Per-session lock serializes a session's turns with support to reconnect-on-failure.

Here is component view of the integration:

![](./diagrams/chat_rtce.drawio.png)

### Get Data Product Lineage and Metrics

The last part of the demonstration is to present a Flink focused lineage, with Data product view.

* The Frontend uses a [DataProductsPage](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/frontend/src/pages/DataProductsPage.tsx) and [StatementGraphPage](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/frontend/src/pages/StatementGraphPage.tsx) 

![](./images/statement_graph.png)

* The backend exposes REST resource in [data_product_resource](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/apps/backend/api/data_product_resource.py) with service and provider, following previous implementation pattern.
* As of now the list of data products come from listing json file in the descriptors folder, and each graph is a static definition from the dbt pipelines.
* To build those json manifest there is a tool, the [build_descriptors](https://github.com/jbcodeforce/streamhouse_c360_demo/blob/main/scripts/build_descriptors.py) which offers a CLI to read dbt manifest.json and creates expected files for the backend:
  ```sh
  cd pipelines
  uv run python ../scripts/build_descriptors.py
  ```

* To get live metrics the backend is calling the Confluent cloud REST API, and depending of the "table_type" being "streaming_table" or "materialized_table" the metrics query is not the same.

## Tests

Both tiers are tested independently, and the test layout mirrors the module layout above — one test file per layer per domain.

### Backend (`apps/backend/tests`, pytest)

Configured in `pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["."]`). Fixtures live in `tests/conftest.py`. The suite is split so most of it runs with
**no infrastructure**:

* **Unit / isolated** — the bulk of the suite. Exercises each layer at its boundary with the dependency mocked:
  * `test_*_models.py` — Pydantic validation and defaults on the model contract.
  * `test_*_inventory.py` / `test_*_seed.py` — CSV load, row↔model mapping, and idempotent seeding.
  * `test_*_api.py`, `test_cors.py` — router behavior via FastAPI `TestClient` (status codes, `404`/`409` mapping, CORS headers), with the DAO stubbed.
* **Postgres integration** — `test_*_postgres.py`. These require a live database and are **auto-skipped when `DATABASE_URL` is unset** (via the   `skip_without_postgres` fixture / `requires_postgres` marker).

Seed isolation: the session-scoped `isolate_seed_csvs` fixture copies the committed seed CSVs to a temp dir and points `*_CSV_PATH` at the copies, so tests never mutate the checked-in seed files.

```sh
cd apps/backend
uv run pytest                 # unit suite (postgres tests skip without DATABASE_URL)
DATABASE_URL=postgresql://dbadmin:localdevonly@localhost:5432/c360db \
  uv run pytest               # include the postgres integration tests
```

### Frontend (`apps/frontend/src`, Vitest + Testing Library)

Vitest with jsdom and React Testing Library; global setup in `src/test/setup.ts`. Tests sit next to the code they cover (`*.test.ts(x)`):

* `src/api/*.test.ts` — the `request()` wrapper and each domain client, with `fetch` mocked: URL/method/body construction, `204` handling, and `ApiError`
  mapping from error bodies.
* `src/pages/*.test.tsx`, `src/components/*.test.tsx` — page and component rendering, routing, form submission, and the confirm/delete flows, with the
  `api/` modules mocked.

```sh
cd apps/frontend
npm test            # vitest run (CI mode)
npm run test:watch  # watch mode
```

