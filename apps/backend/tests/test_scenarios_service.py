"""Tests for scenarios.service — monkeypatched boundaries, no real DB."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from accounts.models import Account
from scenarios import service


NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


def _account(**over) -> Account:
    base = dict(
        account_id=uuid4(), customer_id=uuid4(), account_number=f"CHK-{uuid4().hex[:6]}",
        account_type="CHECKING", currency="USD", balance=0.0, credit_limit=None,
        opened_date=date(2020, 1, 1), closed_date=None, status="ACTIVE",
        created_at=NOW, updated_at=NOW,
    )
    base.update(over)
    return Account(**base)


@pytest.fixture
def svc(monkeypatch):
    monkeypatch.setattr(service.db_sink, "create_many", MagicMock(side_effect=lambda t: t))
    return service


def test_run_returns_scenario_result_with_transactions(svc):
    result = svc.run("fraud-probe")
    assert result.scenario_id == "fraud-probe"
    assert result.pattern == "fct_fraud_probe"
    assert len(result.transactions) == 4   # 3 CHECKING + 1 SAVINGS (benign)
    svc.db_sink.create_many.assert_called_once()


def test_run_merchant_streak(svc):
    result = svc.run("merchant-streak")
    assert result.scenario_id == "merchant-streak"
    assert len(result.transactions) == 3


def test_run_smb_spike(svc):
    result = svc.run("smb-spike")
    assert result.scenario_id == "smb-spike"
    assert len(result.transactions) == 4


def test_unknown_scenario_raises(svc):
    with pytest.raises(svc.UnknownScenarioError):
        svc.run("does-not-exist")
    svc.db_sink.create_many.assert_not_called()


def test_list_scenarios_returns_all_three(svc):
    scenarios = svc.list_scenarios()
    ids = {s.scenario_id for s in scenarios}
    assert ids == {"fraud-probe", "merchant-streak", "smb-spike"}
