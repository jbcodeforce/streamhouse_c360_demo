"""Tests for the /scenarios REST resource — monkeypatched service, no DB."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.scenario_resource import router
from scenarios import service
from scenarios.models import ScenarioDefinition, ScenarioResult, ScenarioTransaction
from transactions.models import Transaction

NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_transaction() -> Transaction:
    return Transaction(
        transaction_id=uuid4(),
        account_id=uuid4(),
        customer_id=uuid4(),
        transaction_type="DEBIT",
        amount=99.00,
        currency="USD",
        description="Test",
        merchant_name="Test Merchant",
        merchant_category="RETAIL",
        channel="ONLINE",
        status="COMPLETED",
        transacted_at=NOW,
        posted_at=NOW,
        created_at=NOW,
    )


def _make_definition(sid: str) -> ScenarioDefinition:
    return ScenarioDefinition(
        scenario_id=sid,
        pattern=f"fct_{sid.replace('-', '_')}",
        label=sid.title(),
        description="Test scenario",
        transactions=[
            ScenarioTransaction(
                account_id=uuid4(),
                customer_id=uuid4(),
                transaction_type="DEBIT",
                amount=5.00,
                description="probe",
                merchant_name="M",
                merchant_category="RETAIL",
                channel="ONLINE",
                offset_seconds=0,
            )
        ],
    )


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_list_scenarios_returns_200(client, monkeypatch):
    monkeypatch.setattr(service, "list_scenarios", lambda: [_make_definition("fraud-probe")])
    resp = client.get("/api/v1/scenarios")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["scenario_id"] == "fraud-probe"


def test_run_scenario_returns_201(client, monkeypatch):
    result = ScenarioResult(
        scenario_id="fraud-probe",
        pattern="fct_fraud_probe",
        label="Fraud Probe",
        triggered_at=NOW,
        transactions=[_make_transaction()],
    )
    monkeypatch.setattr(service, "run", lambda sid: result)
    resp = client.post("/api/v1/scenarios/fraud-probe/run")
    assert resp.status_code == 201
    body = resp.json()
    assert body["scenario_id"] == "fraud-probe"
    assert len(body["transactions"]) == 1


def test_unknown_scenario_returns_404(client, monkeypatch):
    monkeypatch.setattr(service, "run", MagicMock(side_effect=service.UnknownScenarioError("x")))
    resp = client.post("/api/v1/scenarios/no-such/run")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_non_postgres_sink_returns_409(client, monkeypatch):
    monkeypatch.setattr(service, "run", MagicMock(side_effect=service.UnsupportedSinkError("kafka")))
    resp = client.post("/api/v1/scenarios/fraud-probe/run")
    assert resp.status_code == 409
    assert "postgres" in resp.json()["detail"].lower()
