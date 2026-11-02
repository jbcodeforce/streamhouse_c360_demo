"""Tests for scenarios.runner — pure function, no I/O."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scenarios.registry import SCENARIOS
from scenarios.runner import build_transactions, _account_id_for


NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_fraud_probe_builds_correct_count():
    defn = SCENARIOS["fraud-probe"]
    result = build_transactions(defn, now=NOW)
    assert len(result) == len(defn.transactions)


def test_timestamps_shifted_by_offset_seconds():
    defn = SCENARIOS["fraud-probe"]
    result = build_transactions(defn, now=NOW)
    for txn_def, txn_create in zip(defn.transactions, result):
        expected = NOW + timedelta(seconds=txn_def.offset_seconds)
        assert txn_create.transacted_at == expected
        assert txn_create.posted_at == expected


def test_amounts_preserved_exactly():
    defn = SCENARIOS["fraud-probe"]
    result = build_transactions(defn, now=NOW)
    for txn_def, txn_create in zip(defn.transactions, result):
        assert txn_create.amount == txn_def.amount


def test_account_id_resolved_from_account_number():
    """The account_id must match the deterministic uuid5 from the account_number."""
    from scenarios.registry import ACCOUNT_NUMBERS
    defn = SCENARIOS["fraud-probe"]
    result = build_transactions(defn, now=NOW)
    for txn_create, acct_num in zip(result, ACCOUNT_NUMBERS["fraud-probe"]):
        assert txn_create.account_id == _account_id_for(acct_num)


def test_customer_ids_preserved():
    defn = SCENARIOS["merchant-streak"]
    result = build_transactions(defn, now=NOW)
    for txn_def, txn_create in zip(defn.transactions, result):
        assert txn_create.customer_id == txn_def.customer_id


def test_deterministic_given_same_now():
    defn = SCENARIOS["smb-spike"]
    r1 = build_transactions(defn, now=NOW)
    r2 = build_transactions(defn, now=NOW)
    assert [t.transacted_at for t in r1] == [t.transacted_at for t in r2]
    assert [t.amount for t in r1] == [t.amount for t in r2]


def test_all_three_scenarios_build_without_error():
    for sid, defn in SCENARIOS.items():
        result = build_transactions(defn, now=NOW)
        assert len(result) == len(defn.transactions), f"{sid} length mismatch"
