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
from cards.models import Card
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


def _card(account: Account, **over) -> Card:
    base = dict(
        card_id=uuid4(), account_id=account.account_id, card_brand="VISA",
        card_type="DEBIT", card_number=f"4532{uuid4().int % 10**12:012d}",
        expires=date(2030, 1, 1), has_chip=True, credit_limit=None,
        created_at=NOW, updated_at=NOW,
    )
    base.update(over)
    return Card(**base)


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


def test_about_90_percent_card_transactions_on_existing_cards():
    accounts = [_account(), _account(), _account()]
    cards = [_card(a) for a in accounts]
    txns = generator.generate(accounts, cards, count=2000, now=NOW, rng=random.Random(4))

    card_txns = [t for t in txns if t.card_id is not None]
    acct_txns = [t for t in txns if t.card_id is None]
    assert 0.85 <= len(card_txns) / len(txns) <= 0.95
    # card transactions carry only the card; account transactions only the account
    assert all(t.account_id is None for t in card_txns)
    assert all(t.account_id is not None for t in acct_txns)
    # customer is the owner of the card's account
    by_card = {c.card_id: next(a for a in accounts if a.account_id == c.account_id) for c in cards}
    assert all(t.customer_id == by_card[t.card_id].customer_id for t in card_txns)
    assert {t.card_id for t in card_txns} <= set(by_card)


def test_skips_expired_cards_and_cards_of_ineligible_accounts():
    good = _account()
    closed = _account(status="CLOSED")
    usable = _card(good)
    expired = _card(good, expires=date(2020, 1, 1))
    orphan = _card(closed)
    txns = generator.generate([good, closed], [usable, expired, orphan], count=300, now=NOW, rng=random.Random(5))
    assert {t.card_id for t in txns if t.card_id} == {usable.card_id}


def test_card_transactions_never_get_account_only_credits():
    a = _account()
    txns = generator.generate([a], [_card(a)], count=1000, now=NOW, rng=random.Random(6))
    card_credits = [t for t in txns if t.card_id and t.transaction_type == "CREDIT"]
    assert card_credits and all(t.description == "Refund" for t in card_credits)


def test_direct_transactions_are_online_or_transfers_and_cards_are_pos_or_online():
    a = _account()
    txns = generator.generate([a], [_card(a)], count=2000, now=NOW, rng=random.Random(10))
    direct = [t for t in txns if t.card_id is None]
    card = [t for t in txns if t.card_id is not None]
    assert direct and {t.channel for t in direct} <= {"ONLINE", "MOBILE"}
    assert any(t.merchant_category == "TRANSFER" for t in direct)
    assert all(t.currency == "USD" for t in direct)  # no foreign direct transactions
    assert {t.channel for t in card} <= {"POS", "ONLINE"}


def test_prefers_checking_accounts_for_account_transactions():
    chk = _account(account_type="CHECKING")
    sav = _account(account_type="SAVINGS")
    txns = generator.generate([chk, sav], [_card(sav)], count=500, now=NOW, rng=random.Random(7))
    assert {t.account_id for t in txns if t.card_id is None} == {chk.account_id}


def test_without_cards_every_transaction_is_account_based():
    a = _account()
    txns = generator.generate([a], [], count=50, now=NOW, rng=random.Random(8))
    assert all(t.card_id is None and t.account_id == a.account_id for t in txns)


def test_populates_merchant_location_and_includes_foreign_currencies():
    a = _account(currency="USD")
    txns = generator.generate([a], [_card(a)], count=1000, now=NOW, rng=random.Random(9))

    assert all(t.merchant_city and t.merchant_state and t.zip for t in txns)
    foreign = [t for t in txns if t.currency != "USD"]
    assert 0.1 <= len(foreign) / len(txns) <= 0.25
    assert {t.currency for t in foreign} >= {"EUR", "GBP", "JPY"}
    # foreign currency always comes with a foreign merchant location
    foreign_cities = {loc[0] for loc in generator._FOREIGN_LOCATIONS}
    assert all(t.merchant_city in foreign_cities for t in foreign)
    assert all(t.currency == "USD" for t in txns if t.merchant_city not in foreign_cities)


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
    acct = _account()
    monkeypatch.setattr(service.accounts_service, "list_all", lambda: [acct])
    monkeypatch.setattr(service.cards_service, "list_all", lambda: [_card(acct)])
    monkeypatch.setattr(service.db_sink, "create_many", MagicMock(side_effect=lambda t: t))
    return service


def test_generate_inserts_rows(svc):
    txns = svc.generate()
    assert len(txns) == 200
    svc.db_sink.create_many.assert_called_once()
    assert svc.db_sink.create_many.call_args.args[0] is txns


@pytest.fixture
def two_customers(monkeypatch):
    carter, other = _account(), _account()
    carter2 = _account(customer_id=carter.customer_id)
    cards = [_card(carter), _card(carter2), _card(other)]
    monkeypatch.setattr(service.accounts_service, "list_all", lambda: [carter, carter2, other])
    monkeypatch.setattr(service.cards_service, "list_all", lambda: cards)
    monkeypatch.setattr(service.db_sink, "create_many", MagicMock(side_effect=lambda t: t))
    return carter, carter2, other, cards


def test_generate_for_customer_only_uses_that_customers_accounts_and_cards(two_customers):
    carter, carter2, other, cards = two_customers
    txns = service.generate(customer_id=carter.customer_id, count=300)

    assert len(txns) == 300
    assert {t.customer_id for t in txns} == {carter.customer_id}
    assert {t.account_id for t in txns if t.account_id} <= {carter.account_id, carter2.account_id}
    own_cards = {c.card_id for c in cards if c.account_id in {carter.account_id, carter2.account_id}}
    assert {t.card_id for t in txns if t.card_id} <= own_cards
    service.db_sink.create_many.assert_called_once()


def test_generate_honours_count_without_customer(svc):
    assert len(svc.generate(count=7)) == 7


def test_generate_for_unknown_customer_raises(two_customers):
    with pytest.raises(service.NoEligibleAccountsError):
        service.generate(customer_id=uuid4())
    service.db_sink.create_many.assert_not_called()


def test_generate_for_customer_without_active_account_raises(monkeypatch):
    closed = _account(status="CLOSED")
    monkeypatch.setattr(service.accounts_service, "list_all", lambda: [closed, _account()])
    monkeypatch.setattr(service.cards_service, "list_all", lambda: [])
    monkeypatch.setattr(service.db_sink, "create_many", MagicMock())
    with pytest.raises(service.NoEligibleAccountsError):
        service.generate(customer_id=closed.customer_id)


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
    calls = []

    def fake(customer_id=None, count=None):
        calls.append((customer_id, count))
        return txns

    monkeypatch.setattr(service, "generate", fake)
    resp = client.post("/api/v1/transactions/generate")
    assert resp.status_code == 201
    assert len(resp.json()) == 3
    assert calls == [(None, None)]  # default behaviour: no filter, default count


def test_api_generate_passes_customer_id_and_count(client, monkeypatch):
    cid = uuid4()
    calls = []

    def fake(customer_id=None, count=None):
        calls.append((customer_id, count))
        return []

    monkeypatch.setattr(service, "generate", fake)
    resp = client.post(f"/api/v1/transactions/generate?customer_id={cid}&count=20")
    assert resp.status_code == 201
    assert calls == [(cid, 20)]


@pytest.mark.parametrize("query", ["count=0", "count=501", "count=abc", "customer_id=not-a-uuid"])
def test_api_generate_rejects_invalid_params(client, monkeypatch, query):
    monkeypatch.setattr(service, "generate", MagicMock())
    resp = client.post(f"/api/v1/transactions/generate?{query}")
    assert resp.status_code == 422
    service.generate.assert_not_called()


def test_api_generate_accepts_count_bounds(client, monkeypatch):
    monkeypatch.setattr(service, "generate", lambda customer_id=None, count=None: [])
    assert client.post("/api/v1/transactions/generate?count=1").status_code == 201
    assert client.post("/api/v1/transactions/generate?count=500").status_code == 201


def test_api_generate_409_without_accounts(client, monkeypatch):
    def boom(customer_id=None, count=None):
        raise generator.NoEligibleAccountsError("none")

    monkeypatch.setattr(service, "generate", boom)
    resp = client.post("/api/v1/transactions/generate")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "No active accounts available"


def test_api_generate_409_for_unknown_customer(client, monkeypatch):
    monkeypatch.setattr(service.accounts_service, "list_all", lambda: [_account()])
    monkeypatch.setattr(service.cards_service, "list_all", lambda: [])
    monkeypatch.setattr(service.db_sink, "create_many", MagicMock())
    resp = client.post(f"/api/v1/transactions/generate?customer_id={uuid4()}&count=5")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "No active accounts available"
