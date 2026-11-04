"""POST /transactions/generate: generator, service, and API behaviour."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from accounts.models import Account
from api.transaction_resource import router
from transactions import generator, service

NOW = datetime(2026, 10, 22, 12, 0, 30, 123456, tzinfo=timezone.utc)


def _account(**over) -> Account:
    base = dict(
        account_id=uuid4(), customer_id=uuid4(), account_number=f"CHK-{uuid4().hex[:6]}",
        account_type="CHECKING", currency="USD", balance=0.0, credit_limit=None,
        opened_date=date(2020, 1, 1), closed_date=None, status="ACTIVE",
        created_at=NOW, updated_at=NOW,
    )
    base.update(over)
    return Account(**base)


# ---------------------------------------------------------------------------
# generator
# ---------------------------------------------------------------------------

def test_generates_200_with_quarter_hour_progression_from_seven_days_ago():
    accounts = [_account(), _account()]
    txns = generator.generate(accounts, now=NOW, rng=random.Random(1))

    assert len(txns) == 200
    start = (NOW - timedelta(days=7)).replace(microsecond=0)
    assert txns[0].transacted_at == start
    for prev, nxt in zip(txns, txns[1:]):
        assert nxt.transacted_at - prev.transacted_at == timedelta(minutes=15)
    assert all(t.posted_at == t.transacted_at for t in txns)
    assert len({t.transaction_id for t in txns}) == 200


def test_uses_only_existing_active_accounts_and_their_customer():
    good = [_account(), _account()]
    closed = _account(closed_date=date(2024, 1, 1))
    inactive = _account(status="CLOSED")
    txns = generator.generate(good + [closed, inactive], now=NOW, rng=random.Random(2))

    pairs = {(a.account_id, a.customer_id) for a in good}
    assert {(t.account_id, t.customer_id) for t in txns} <= pairs


def test_raises_without_eligible_accounts():
    with pytest.raises(generator.NoEligibleAccountsError):
        generator.generate([_account(status="CLOSED")], now=NOW)
    with pytest.raises(generator.NoEligibleAccountsError):
        generator.generate([], now=NOW)


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------

@pytest.fixture
def svc(monkeypatch):
    monkeypatch.setattr(service.accounts_service, "list_all", lambda: [_account()])
    monkeypatch.setattr(service.db_sink, "create_many", MagicMock(side_effect=lambda t: t))
    return service


def test_generate_inserts_rows(svc):
    txns = svc.generate()
    assert len(txns) == 200
    svc.db_sink.create_many.assert_called_once()
    assert svc.db_sink.create_many.call_args.args[0] is txns


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_api_generate_returns_201_with_transactions(client, monkeypatch):
    txns = generator.generate([_account()], count=3, now=NOW, rng=random.Random(3))
    monkeypatch.setattr(service, "generate", lambda: txns)
    resp = client.post("/api/v1/transactions/generate")
    assert resp.status_code == 201
    assert len(resp.json()) == 3


def test_api_generate_409_without_accounts(client, monkeypatch):
    def boom():
        raise generator.NoEligibleAccountsError("none")

    monkeypatch.setattr(service, "generate", boom)
    resp = client.post("/api/v1/transactions/generate")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "No active accounts available"
