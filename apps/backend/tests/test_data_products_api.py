"""/api/v1/data-products endpoints: list, graph, status, node metrics.

Postgres bootstrap mocked + GRAPH_DATA_MODE=mock (no infra) exactly like
test_cors.py. The fixture
fully resets the imported app modules in sys.modules on teardown so suites
that reimport ``main`` afterwards start from a clean module graph.
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
    env_patch = patch.dict("os.environ", {
        "GRAPH_DATA_MODE": "mock",
        # Isolate from the repo's real .env so app startup never attempts a real
        # connection (it may point at live/remote infra or enable seeding).
        "ENV_CONFIG_FILE": "/nonexistent/.env.test",
        "KAFKA_BOOTSTRAP_SERVERS": "mock:9092",
        "SCHEMA_REGISTRY_URL": "http://mock-sr",
        "SCHEMA_REGISTRY_API_KEY": "key",
        "SCHEMA_REGISTRY_API_SECRET": "secret",
    })
    env_patch.start()
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
    assert r.status_code == 200 and len(body["nodes"]) == 11 and len(body["edges"]) == 11


def test_status_rollup(client):
    r = client.get("/api/v1/data-products/c360/status")
    assert r.status_code == 200 and r.json()["rollup"] == {"running": 8, "total": 8, "lagging": 0}


def test_node_metrics(client):
    r = client.get("/api/v1/data-products/c360/nodes/src_customers/metrics")
    assert r.status_code == 200 and r.json()["phase"] == "RUNNING"


def test_source_node_metrics_returns_200_unknown_not_500(client):
    """topic_customers is a SOURCE node, absent from STATEMENT_FIXTURES.
    Must degrade to UNKNOWN (200), never raise KeyError (500)."""
    r = client.get("/api/v1/data-products/c360/nodes/topic_customers/metrics")
    assert r.status_code == 200 and r.json()["phase"] == "UNKNOWN"


def test_cost_route_returns_cost_response(client):
    r = client.get("/api/v1/data-products/c360/cost")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["amount"] > 0
    assert body["cfu"] is not None
    # pool_ids are the product's owned pools from the descriptor (not hardcoded,
    # since real ids replace the build-time placeholders after a live regen).
    from data_products import descriptor  # noqa: PLC0415

    graph = descriptor.get_graph("c360")
    expected_pools = sorted(
        {n.compute_pool_id for n in graph.nodes if n.type == "statement" and not n.external and n.compute_pool_id}
    )
    assert body["pool_ids"] == expected_pools and expected_pools


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


@pytest.fixture(scope="module")
def live_client():
    """Same wiring as ``client``, but GRAPH_DATA_MODE=live with NO Confluent
    credentials configured — proves the live endpoint path degrades (never
    5xx) when Confluent Cloud is unreachable/unconfigured.

    ``ENV_CONFIG_FILE`` is pointed at a nonexistent path so a real repo
    ``.env`` (which may carry real Flink/Confluent credentials for manual
    testing) is never loaded here — this fixture must exercise the
    no-credentials code path, not whatever happens to be on disk. The
    FLINK_*/CONFLUENT_CLOUD_* keys are also deleted from the process
    environment (if present) for the same reason.
    """
    env_patch = patch.dict("os.environ", {
        "GRAPH_DATA_MODE": "live",
        "ENV_CONFIG_FILE": "/nonexistent/.env.test-no-creds",
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


def test_live_mode_status_degrades_to_200(live_client):
    r = live_client.get("/api/v1/data-products/c360/status")
    assert r.status_code == 200
    assert r.json()["rollup"]["total"] == 8


def test_live_mode_node_metrics_degrades_to_200(live_client):
    r = live_client.get("/api/v1/data-products/c360/nodes/src_customers/metrics")
    assert r.status_code == 200
