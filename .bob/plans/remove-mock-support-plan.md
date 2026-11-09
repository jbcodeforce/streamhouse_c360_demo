# Plan: Remove Mock Support from Backend

## Top-Level Overview
Remove all mock data files, mock provider implementations, and `*_DATA_MODE` configuration settings across all backend domains (`data_products`, `analytics`, `chat`, `scenarios`). The backend will strictly run live integrations (with existing graceful degradation on unconfigured/failing infrastructure), simplifying the architecture and eliminating dual-path maintenance.

---

## Sub-Tasks

### Sub-Task 1: Remove Data Mode Configuration Flags
- **Intent**: Eliminate `GRAPH_DATA_MODE`, `ANALYTICS_DATA_MODE`, `CEP_DATA_MODE`, and `CHAT_DATA_MODE` configuration options from `config.py` and `.env.example`.
- **Expected Outcomes**:
  - `Settings` in `apps/backend/config.py` no longer defines or logs any `*_DATA_MODE` variables.
  - `apps/backend/.env.example` has all mock data mode entries and documentation comments removed.
  - `Settings.summary()` only reports real live service coordinates.
- **Todo List**:
  - [x] Remove `GRAPH_DATA_MODE`, `CHAT_DATA_MODE`, `ANALYTICS_DATA_MODE`, and `CEP_DATA_MODE` from `Settings` class in `apps/backend/config.py`.
  - [x] Update `Settings.summary()` in `apps/backend/config.py` to remove data mode keys.
  - [x] Clean up `.env.example` to remove all data mode comments and defaults.
- **Relevant Context**:
  - `apps/backend/config.py:68-114`
  - `apps/backend/.env.example:29-34,68-73`
- **Status**: `[x] done`

---

### Sub-Task 2: Remove Mock Support from Data Products Domain
- **Intent**: Remove synthetic statement fixtures and `MockProvider`, making `LiveProvider` the sole status, metrics, and cost provider for data products.
- **Expected Outcomes**:
  - `data_products/mock_data.py` is deleted.
  - `MockProvider` and mode branching are removed from `data_products/providers.py`.
  - `get_provider()` always returns a `LiveProvider` instance (or is simplified).
  - All status/metrics/cost requests query Confluent Cloud / Flink with existing graceful degradation (e.g. UNKNOWN phase when offline).
- **Todo List**:
  - [x] Delete `apps/backend/data_products/mock_data.py`.
  - [x] Remove `MockProvider` class and `mock_data` imports from `apps/backend/data_products/providers.py`.
  - [x] Simplify `get_provider()` in `apps/backend/data_products/providers.py` to instantiate `LiveProvider`.
- **Relevant Context**:
  - `apps/backend/data_products/mock_data.py`
  - `apps/backend/data_products/providers.py:82-154,369-387`
  - `apps/backend/data_products/service.py`
- **Status**: `[x] done`

---

### Sub-Task 3: Remove Mock Support from Analytics Domain
- **Intent**: Remove static profile fixtures, mock aggregation logic, and mode-switching from the C360 analytics dashboard and customer lookup.
- **Expected Outcomes**:
  - `analytics/mock_data.py` is deleted.
  - `mock_aggregate()` in `analytics/aggregate.py` is removed; shared utilities (`_num`, `_COUNTRY_TOP_N`) are consolidated into `analytics/crm_aggregate.py`.
  - `analytics/providers.py` no longer checks `_mode()` or falls back to `_mock_profile()`.
  - `analytics/service.py` directly executes CRM snapshot queries and returns `source_mode="live"`.
- **Todo List**:
  - [x] Delete `apps/backend/analytics/mock_data.py`.
  - [x] Remove `mock_aggregate()` and consolidate aggregation helper logic into `apps/backend/analytics/crm_aggregate.py` / `apps/backend/analytics/aggregate.py`.
  - [x] Remove `_mode()`, `_mock_profile()`, and mock branching from `apps/backend/analytics/providers.py`.
  - [x] Remove mock branching from `apps/backend/analytics/service.py` so `get_data_analytics()` and profile lookups always query live snapshot tables.
- **Relevant Context**:
  - `apps/backend/analytics/mock_data.py`
  - `apps/backend/analytics/aggregate.py`
  - `apps/backend/analytics/crm_aggregate.py`
  - `apps/backend/analytics/providers.py:86-94,142-178`
  - `apps/backend/analytics/service.py:51-76`
- **Status**: `[x] done`

---

### Sub-Task 4: Remove Mock/Stub Mode from Chat Domain
- **Intent**: Eliminate `CHAT_DATA_MODE="stub"` branching so the assistant chat runs strictly against the live LLM + RTCE context-engine MCP agent.
- **Expected Outcomes**:
  - `chat/service.py` no longer checks `CHAT_DATA_MODE` or returns stub canned greetings/replies.
  - Missing LLM/MCP configurations or runtime agent failures return clean error responses with `source_mode="error"`, while successful responses return `source_mode="live"`.
  - `get_welcome()` returns the configured greeting with `source_mode="live"`.
- **Todo List**:
  - [x] Remove `CHAT_DATA_MODE` checks and `_stub_reply()` from `apps/backend/chat/service.py`.
  - [x] Update `_live_ready()` in `apps/backend/chat/service.py` to check presence of required LLM/MCP credentials.
  - [x] Update `get_welcome()` and `get_reply()` to return appropriate live or unconfigured error responses.
- **Relevant Context**:
  - `apps/backend/chat/service.py:29-61`
  - `apps/backend/chat/models.py`
- **Status**: `[x] done`

---

### Sub-Task 5: Refactor and Clean Up Test Suite
- **Intent**: Remove mock-provider tests and update API and service tests to exercise live providers and boundary client mocks without relying on backend mock modes.
- **Expected Outcomes**:
  - `test_data_products_mock.py` and `test_analytics_aggregate.py` are deleted.
  - `test_config.py` asserts the updated settings summary without data mode keys.
  - `test_data_products_api.py`, `test_analytics_api.py`, `test_analytics_service.py`, `test_chat_api.py`, and `test_chat_service.py` run against live providers (using standard unittest/pytest boundary mocks or verifying graceful unconfigured degradation).
- **Todo List**:
  - [x] Delete `apps/backend/tests/test_data_products_mock.py` and `apps/backend/tests/test_analytics_aggregate.py`.
  - [x] Update `apps/backend/tests/test_config.py` to remove data mode assertions.
  - [x] Update `apps/backend/tests/test_data_products_api.py` to remove `GRAPH_DATA_MODE` and test live provider responses/degradation.
  - [x] Update `apps/backend/tests/test_analytics_api.py` and `apps/backend/tests/test_analytics_service.py` to remove `ANALYTICS_DATA_MODE` and test live CRM assembly / lookups.
  - [x] Update `apps/backend/tests/test_chat_api.py` and `apps/backend/tests/test_chat_service.py` to remove `CHAT_DATA_MODE` references.
- **Relevant Context**:
  - `apps/backend/tests/test_data_products_mock.py`
  - `apps/backend/tests/test_analytics_aggregate.py`
  - `apps/backend/tests/test_data_products_api.py`
  - `apps/backend/tests/test_analytics_api.py`
  - `apps/backend/tests/test_analytics_service.py`
  - `apps/backend/tests/test_config.py`
  - `apps/backend/tests/test_chat_api.py`
  - `apps/backend/tests/test_chat_service.py`
- **Status**: `[x] done`

---

### Sub-Task 6: Validation and Verification
- **Intent**: Run the full backend pytest test suite to ensure all unit and integration tests pass without warnings or regressions.
- **Expected Outcomes**:
  - All test files in `apps/backend/tests/` pass cleanly with `uv run pytest`.
- **Todo List**:
  - [x] Run full test suite with `uv run pytest` from `apps/backend` (250 passed, 27 skipped).
  - [x] Fix any remaining references or broken assertions (removed stale `ANALYTICS_DATA_MODE` / "mock" wording in `analytics/confluent_sql_client.py`, `analytics/models.py`, `api/analytics_resource.py`).
- **Relevant Context**:
  - `apps/backend/pyproject.toml`
  - `apps/backend/tests/`
- **Status**: `[x] done`
