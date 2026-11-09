"""/api/v1/analytics endpoints: the C360 snapshot dashboard.

Postgres bootstrap mocked; tests live CRM snapshot queries, profile lookups,
and graceful degradation when Confluent Cloud / Flink is unconfigured.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_THOMAS_ID = "00000000-0000-0000-0000-678901234568"

_SAMPLE_SUMMARY = {
    "qscope": "ALL",
    "total_customers": 10,
    "total_accounts": 31,
    "total_balance": Decimal("343671.00"),
    "total_transactions": 512,
    "total_txn_amount": Decimal("41819.00"),
    "avg_age": 41.8,
    "missing_email": 1,
    "missing_phone": 2,
    "complete": 7,
}
_SAMPLE_BY_SEGMENT = [
    {"customer_segment": "PRIVATE", "customer_count": 6, "total_balance": Decimal("260601")},
    {"customer_segment": "SMB", "customer_count": 4, "total_balance": Decimal("83070")},
]
_SAMPLE_BY_GENERATION = [
    {"generation_segment": "GEN_Z", "customer_count": 3, "total_balance": Decimal("50000")},
]
_SAMPLE_BY_GENDER = [
    {"gender": "FEMALE", "customer_count": 5, "total_balance": Decimal("180000")},
]
_SAMPLE_BY_COUNTRY = [
    {"country": "US", "customer_count": 10, "total_balance": Decimal("343671")},
]

_SAMPLE_CUSTOMER_ROW = {
    "customer_id": _THOMAS_ID,
    "first_name": "Thomas",
    "last_name": "Brennan",
    "customer_segment": "SMB",
    "generation_segment": "MILLENNIAL",
    "gender": "MALE",
    "age_years": 42,
    "city": "Austin",
    "state": "TX",
    "country": "US",
    "customer_since": "2020-01-15",
    "days_since_registration": 1500,
    "missing_email_flag": 0,
    "missing_phone_flag": 0,
    "account_count": 6,
    "total_balance": 318400.00,
    "txn_count": 512,
    "txn_total": 54321.00,
}


def _reset_modules() -> None:
    for mod in list(sys.modules):
        if mod in ("config", "main") or mod.startswith(("customers", "api", "data_products", "analytics")):
            del sys.modules[mod]


@pytest.fixture(scope="module")
def client():
    """Client fixture with unconfigured Confluent/Flink credentials to verify
    graceful degradation across analytics endpoints."""
    env_patch = patch.dict("os.environ", {
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
        "FLINK_COMPUTE_POOL_ID", "FLINK_REST_ENDPOINT", "FLINK_CATALOG", "FLINK_DATABASE",
    ):
        os.environ.pop(key, None)
    _reset_modules()

    with patch("bootstrap.init_and_seed"):
        import main  # noqa: PLC0415 — intentional late import after env patch
        with TestClient(main.app) as test_client:
            yield test_client

    env_patch.stop()
    _reset_modules()


def test_live_mode_degrades_to_empty_200(client):
    r = client.get("/api/v1/analytics/c360-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "live"
    assert body["row_count"] == 0
    assert body["total_customers"] == 0
    assert body["by_segment"] == []
    assert "query_ms" in body and body["query_ms"] >= 0


def test_c360_profile_with_mocked_crm_result_sets(client, monkeypatch):
    from analytics import service

    monkeypatch.setattr(
        service.providers,
        "fetch_crm_result_sets",
        lambda: (_SAMPLE_SUMMARY, _SAMPLE_BY_SEGMENT, _SAMPLE_BY_GENERATION, _SAMPLE_BY_GENDER, _SAMPLE_BY_COUNTRY),
    )
    r = client.get("/api/v1/analytics/c360-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "live"
    assert body["row_count"] == 10
    assert body["total_customers"] == 10
    assert body["total_accounts"] == 31
    assert body["by_segment"][0] == {"label": "PRIVATE", "count": 6}
    assert body["data_quality"]["missing_phone"] == 2
    for key in ("by_segment", "by_generation", "by_gender", "by_country", "balance_by_segment"):
        assert isinstance(body[key], list) and body[key]
    assert body["generated_at"].endswith("Z")
    assert "query_ms" in body and body["query_ms"] >= 0


# --- Customer by-id profile (name-to-id resolution lives in /customers) ----

def test_customer_profile_by_id_with_mocked_provider(client, monkeypatch):
    from analytics import service

    monkeypatch.setattr(
        service.providers,
        "get_customer_profile",
        lambda cid: (_SAMPLE_CUSTOMER_ROW, "live") if cid == _THOMAS_ID else (None, "live"),
    )
    r = client.get(f"/api/v1/analytics/c360-profile/customer/{_THOMAS_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "live"
    assert body["first_name"] == "Thomas" and body["last_name"] == "Brennan"
    assert body["customer_segment"] == "SMB"
    assert body["account_count"] == 6
    assert body["total_balance"] == 318400.00
    assert body["txn_count"] == 512
    assert "query_ms" in body and body["query_ms"] >= 0


def test_customer_profile_unknown_id_404(client):
    r = client.get("/api/v1/analytics/c360-profile/customer/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_customer_profile_malformed_id_404(client):
    # Characters outside the id charset are rejected before any query.
    r = client.get("/api/v1/analytics/c360-profile/customer/' OR '1'='1")
    assert r.status_code == 404


# --- RTCE / Lightning endpoints -------------------------------------------

def test_rtce_customer_profile_by_id_with_mocked_provider(client, monkeypatch):
    from analytics import service

    monkeypatch.setattr(
        service.providers,
        "get_customer_profile_rtce",
        lambda cid: (_SAMPLE_CUSTOMER_ROW, "live") if cid == _THOMAS_ID else (None, "live"),
    )
    r = client.get(f"/api/v1/analytics/c360-profile/rtce/customer/{_THOMAS_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "live"
    assert body["first_name"] == "Thomas"
    assert body["txn_count"] == 512
    assert "query_ms" in body and body["query_ms"] >= 0


def test_rtce_customer_profile_unknown_id_404(client):
    r = client.get("/api/v1/analytics/c360-profile/rtce/customer/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
