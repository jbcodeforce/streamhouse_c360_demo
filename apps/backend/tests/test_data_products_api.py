"""/api/v1/data-products endpoints: list, graph, status, node metrics, cost.

Postgres bootstrap mocked; tests live provider responses and graceful
degradation when Confluent Cloud is unconfigured or unreachable.
The fixture fully resets the imported app modules in sys.modules on teardown so
suites that reimport ``main`` afterwards start from a clean module graph.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _reset_modules() -> None:
    """Drop the app's modules AND their packages from sys.modules.

    Popping a submodule alone leaves a stale attribute on the cached package
    object, so a later ``from package import submodule`` returns the old
    module instead of reimporting. Clearing the packages too forces a clean
    reimport for suites that run after this one.
    """
    for mod in list(sys.modules):
        if mod in ("config", "main") or mod.startswith(("customers", "api", "data_products")):
            del sys.modules[mod]


@pytest.fixture(scope="module")
def client():
    """Client fixture with unconfigured Confluent credentials to verify
    graceful degradation across all data product endpoints."""
    env_patch = patch.dict("os.environ", {
        # Isolate from the repo's real .env so app startup never attempts a real
        # connection (it may point at live/remote infra or enable seeding).
        "ENV_CONFIG_FILE": "/nonexistent/.env.test",
        "KAFKA_BOOTSTRAP_SERVERS": "mock:9092",
        "SCHEMA_REGISTRY_URL": "http://mock-sr",
        "SCHEMA_REGISTRY_API_KEY": "key",
        "SCHEMA_REGISTRY_API_SECRET": "secret",
    })
    env_patch.start()
    for key in (
        "CONFLUENT_CLOUD_API_KEY", "CONFLUENT_CLOUD_API_SECRET",
        "FLINK_API_KEY", "FLINK_API_SECRET", "FLINK_ORG_ID", "FLINK_ENV_ID",
        "FLINK_COMPUTE_POOL_ID", "FLINK_REST_ENDPOINT",
    ):
        os.environ.pop(key, None)
    _reset_modules()

    with patch("bootstrap.init_and_seed"):
        import main  # noqa: PLC0415 — intentional late import after env patch
        with TestClient(main.app) as test_client:
            yield test_client

    env_patch.stop()
    _reset_modules()


def test_list_products(client):
    r = client.get("/api/v1/data-products")
    assert r.status_code == 200 and r.json()[0]["id"] == "c360"


def test_graph_endpoint_shape(client):
    r = client.get("/api/v1/data-products/c360/graph")
    body = r.json()
    assert r.status_code == 200 and len(body["nodes"]) == 15 and len(body["edges"]) == 17


def test_status_rollup_degrades_gracefully(client):
    r = client.get("/api/v1/data-products/c360/status")
    assert r.status_code == 200
    data = r.json()
    assert data["rollup"] == {"running": 0, "total": 11, "lagging": 0}
    assert all(s["phase"] == "UNKNOWN" for s in data["statements"])


def test_status_rollup_with_live_client_data(client, monkeypatch):
    from data_products import providers
    from data_products.providers import LiveProvider

    class _MockClient:
        def list_statement_phases(self):
            return {"src_customers": "RUNNING"}

        def list_materialized_tables(self):
            return {"fct_c360_profile": {"phase": "RUNNING", "uid": "uid-1"}}

        def list_statements(self):
            return {}

        def get_statement_metrics(self, *a, **k):
            return {}

        def get_materialized_table_metrics(self, *a, **k):
            return {}

        def get_flink_pool_costs(self, *a, **k):
            return {}

        def get_compute_pool_cfu(self, *a, **k):
            return 2.0

    monkeypatch.setattr(providers, "get_provider", lambda: LiveProvider(client=_MockClient()))
    r = client.get("/api/v1/data-products/c360/status")
    assert r.status_code == 200
    assert r.json()["rollup"]["running"] == 2


def test_node_metrics_degrades_gracefully(client):
    r = client.get("/api/v1/data-products/c360/nodes/src_customers/metrics")
    assert r.status_code == 200 and r.json()["phase"] == "UNKNOWN"


def test_node_metrics_with_live_client_data(client, monkeypatch):
    from data_products import providers
    from data_products.providers import LiveProvider

    class _MockClient:
        def list_statement_phases(self):
            return {"fct_c360_profile": "RUNNING"}

        def list_materialized_tables(self):
            return {"fct_c360_profile": {"phase": "RUNNING", "uid": "uid-src", "sql": "SELECT 1", "created_at": "2026-01-01T00:00:00Z"}}

        def list_statements(self):
            return {}

        def get_statement_metrics(self, *a, **k):
            return {}

        def get_materialized_table_metrics(self, *a, **k):
            return {"messages_in_per_sec": 42.0}

        def get_flink_pool_costs(self, *a, **k):
            return {}

        def get_compute_pool_cfu(self, *a, **k):
            return None

    monkeypatch.setattr(providers, "get_provider", lambda: LiveProvider(client=_MockClient()))
    r = client.get("/api/v1/data-products/c360/nodes/fct_c360_profile/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "RUNNING"
    assert body["messages_in_per_sec"] == 42.0
    assert body["sql"] == "SELECT 1"


def test_source_node_metrics_returns_200_unknown_not_500(client):
    """topic_customers is a SOURCE node. Must degrade to UNKNOWN (200), never 500."""
    r = client.get("/api/v1/data-products/c360/nodes/topic_customers/metrics")
    assert r.status_code == 200 and r.json()["phase"] == "UNKNOWN"


def test_cost_route_unconfigured_is_unavailable(client):
    r = client.get("/api/v1/data-products/c360/cost")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False


def test_cost_route_with_live_costs(client, monkeypatch):
    from data_products import descriptor, providers
    from data_products.providers import LiveProvider

    graph = descriptor.get_graph("c360")
    pools = sorted(
        {n.compute_pool_id for n in graph.nodes if n.type == "statement" and not n.external and n.compute_pool_id}
    )

    class _MockClient:
        def list_statement_phases(self):
            return {}

        def list_materialized_tables(self):
            return {}

        def list_statements(self):
            return {}

        def get_statement_metrics(self, *a, **k):
            return {}

        def get_materialized_table_metrics(self, *a, **k):
            return {}

        def get_flink_pool_costs(self, *a, **k):
            return {p: 15.50 for p in pools}

        def get_compute_pool_cfu(self, pool_id: str):
            return 2.0

    monkeypatch.setattr(providers, "get_provider", lambda: LiveProvider(client=_MockClient()))
    r = client.get("/api/v1/data-products/c360/cost")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["amount"] > 0
    assert body["cfu"] is not None
    assert body["pool_ids"] == pools


def test_unknown_product_cost_404(client):
    assert client.get("/api/v1/data-products/nope/cost").status_code == 404


def test_unknown_product_graph_404(client):
    assert client.get("/api/v1/data-products/nope/graph").status_code == 404


def test_unknown_product_status_404(client):
    assert client.get("/api/v1/data-products/nope/status").status_code == 404


def test_unknown_node_metrics_404(client):
    assert client.get("/api/v1/data-products/c360/nodes/nope/metrics").status_code == 404


def test_unknown_product_metrics_404(client):
    assert client.get("/api/v1/data-products/nope/nodes/src_customers/metrics").status_code == 404
