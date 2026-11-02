"""/api/v1/analytics endpoints: the C360 snapshot dashboard.

Wired to SINK=kafka exactly like test_data_products_api.py, Kafka producers
mocked at the boundary. Two fixtures: the default ``client`` (ANALYTICS_DATA_MODE
=mock) and ``live_client`` (=live with NO Confluent credentials) which proves
the live path degrades to an empty 200 rather than 5xx.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _reset_modules() -> None:
    for mod in list(sys.modules):
        if mod in ("config", "main") or mod.startswith(("customers", "api", "data_products", "analytics")):
            del sys.modules[mod]


@pytest.fixture(scope="module")
def client():
    env_patch = patch.dict("os.environ", {
        "SINK": "kafka",
        "ANALYTICS_DATA_MODE": "mock",
        # Point at a nonexistent env file so the repo's real .env (which may set
        # KAFKA_SEED_ON_START etc. and make startup attempt a real connection) is
        # never loaded — this suite must exercise the mock path only.
        "ENV_CONFIG_FILE": "/nonexistent/.env.test-mock",
        "KAFKA_SEED_ON_START": "false",
        "KAFKA_BOOTSTRAP_SERVERS": "mock:9092",
        "SCHEMA_REGISTRY_URL": "http://mock-sr",
        "SCHEMA_REGISTRY_API_KEY": "key",
        "SCHEMA_REGISTRY_API_SECRET": "secret",
    })
    env_patch.start()
    _reset_modules()

    with patch("customers.kafka_producer.produce_create"), \
         patch("customers.kafka_producer.produce_update"):
        import main  # noqa: PLC0415 — intentional late import after env patch
        with TestClient(main.app) as test_client:
            yield test_client

    env_patch.stop()
    _reset_modules()


def test_c360_profile_mock_payload(client):
    r = client.get("/api/v1/analytics/c360-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "mock"
    assert body["row_count"] == 10
    assert body["total_customers"] == 10
    assert body["total_accounts"] == 31
    assert body["by_segment"][0] == {"label": "PRIVATE", "count": 6}
    assert body["data_quality"]["missing_phone"] == 2


def test_c360_profile_has_all_distributions(client):
    body = client.get("/api/v1/analytics/c360-profile").json()
    for key in ("by_segment", "by_generation", "by_gender", "by_country", "balance_by_segment"):
        assert isinstance(body[key], list) and body[key]
    assert body["generated_at"].endswith("Z")


def test_query_ms_present_on_payloads(client):
    agg = client.get("/api/v1/analytics/c360-profile").json()
    assert "query_ms" in agg and isinstance(agg["query_ms"], (int, float)) and agg["query_ms"] >= 0

    prof = client.get(f"/api/v1/analytics/c360-profile/customer/{_THOMAS_ID}").json()
    assert prof["query_ms"] >= 0


# --- Customer by-id profile (name-to-id resolution lives in /customers) ----

_THOMAS_ID = "00000000-0000-0000-0000-678901234568"


def test_customer_profile_by_id(client):
    r = client.get(f"/api/v1/analytics/c360-profile/customer/{_THOMAS_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["first_name"] == "Thomas" and body["last_name"] == "Brennan"
    assert body["customer_segment"] == "SMB"
    assert body["account_count"] == 6
    assert body["total_balance"] == 318400.00
    assert body["txn_count"] == 512


def test_customer_profile_unknown_id_404(client):
    r = client.get("/api/v1/analytics/c360-profile/customer/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_customer_profile_malformed_id_404(client):
    # Characters outside the id charset are rejected before any query.
    r = client.get("/api/v1/analytics/c360-profile/customer/' OR '1'='1")
    assert r.status_code == 404


# --- RTCE / Lightning endpoints (mock mode mirrors the Flink endpoints) ----


def test_rtce_customer_profile_by_id(client):
    r = client.get(f"/api/v1/analytics/c360-profile/rtce/customer/{_THOMAS_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["first_name"] == "Thomas"
    assert body["txn_count"] == 512


def test_rtce_customer_profile_unknown_id_404(client):
    r = client.get("/api/v1/analytics/c360-profile/rtce/customer/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@pytest.fixture(scope="module")
def live_client():
    """ANALYTICS_DATA_MODE=live with NO Confluent credentials — the live snapshot
    path must degrade to an empty 200, never 5xx. ENV_CONFIG_FILE points at a
    nonexistent path so a real repo .env (with real Flink creds) is never loaded.
    """
    env_patch = patch.dict("os.environ", {
        "SINK": "kafka",
        "ANALYTICS_DATA_MODE": "live",
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
        "FLINK_COMPUTE_POOL_ID", "FLINK_REST_ENDPOINT", "FLINK_CATALOG", "FLINK_DATABASE",
    ):
        os.environ.pop(key, None)
    _reset_modules()

    with patch("customers.kafka_producer.produce_create"), \
         patch("customers.kafka_producer.produce_update"):
        import main  # noqa: PLC0415 — intentional late import after env patch
        with TestClient(main.app) as test_client:
            yield test_client

    env_patch.stop()
    _reset_modules()


def test_live_mode_degrades_to_empty_200(live_client):
    r = live_client.get("/api/v1/analytics/c360-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "live"
    assert body["row_count"] == 0
    assert body["total_customers"] == 0
    assert body["by_segment"] == []
