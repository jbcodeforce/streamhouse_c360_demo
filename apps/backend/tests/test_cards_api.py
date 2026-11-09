"""Cards API tests against a bare app (no lifespan/DB/Kafka)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.card_resource import router
from cards import service
from cards.models import Card


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def _card(account_id) -> Card:
    now = datetime.now(tz=timezone.utc)
    return Card(
        card_id=uuid4(), account_id=account_id, card_brand="VISA",
        card_type="DEBIT", card_number="4532010000079192",
        expires=date(2027, 1, 28), has_chip=True, credit_limit=None,
        created_at=now, updated_at=now,
    )


def test_list_by_account(client, monkeypatch):
    aid = uuid4()
    captured = {}

    def _by_account(account_id):
        captured["aid"] = account_id
        return [_card(account_id)]

    monkeypatch.setattr(service, "list_by_account", _by_account)
    resp = client.get(f"/api/v1/cards?account_id={aid}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert captured["aid"] == aid


def test_list_all_when_no_account_id(client, monkeypatch):
    monkeypatch.setattr(service, "list_all", lambda: [_card(uuid4()), _card(uuid4())])
    resp = client.get("/api/v1/cards")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
