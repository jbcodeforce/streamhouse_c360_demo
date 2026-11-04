"""Closing an account stamps closed_date server-side."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from accounts import service
from accounts.models import Account, AccountUpdate


def _account(**over) -> Account:
    now = datetime.now(tz=timezone.utc)
    base = dict(
        account_id=uuid4(), customer_id=uuid4(), account_number="ACC-1",
        account_type="CHECKING", currency="USD", balance=10.0, credit_limit=None,
        opened_date=date(2021, 1, 1), closed_date=None, status="ACTIVE",
        created_at=now, updated_at=now,
    )
    base.update(over)
    return Account(**base)


@pytest.fixture
def svc(monkeypatch):
    monkeypatch.setattr(service.db_sink, "update", MagicMock())
    return service


def test_close_stamps_closed_date_when_absent(svc):
    svc.db_sink.update.return_value = _account(status="CLOSED", closed_date=date.today())
    svc.update(uuid4(), AccountUpdate(status="CLOSED"))
    passed = svc.db_sink.update.call_args.args[1]
    assert passed.closed_date == date.today()


def test_close_preserves_explicit_closed_date(svc):
    explicit = date(2020, 6, 1)
    svc.db_sink.update.return_value = _account(status="CLOSED", closed_date=explicit)
    svc.update(uuid4(), AccountUpdate(status="CLOSED", closed_date=explicit))
    passed = svc.db_sink.update.call_args.args[1]
    assert passed.closed_date == explicit


def test_non_close_update_does_not_stamp(svc):
    svc.db_sink.update.return_value = _account(balance=99.0)
    svc.update(uuid4(), AccountUpdate(balance=99.0))
    passed = svc.db_sink.update.call_args.args[1]
    assert passed.closed_date is None
