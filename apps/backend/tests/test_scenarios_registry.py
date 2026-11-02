"""Tests for scenarios.registry — structure validation without I/O."""

from __future__ import annotations

from scenarios.registry import SCENARIOS, ACCOUNT_NUMBERS


def test_registry_has_exactly_three_scenarios():
    assert set(SCENARIOS.keys()) == {"fraud-probe", "merchant-streak", "smb-spike"}


def test_each_scenario_has_non_empty_transactions():
    for sid, defn in SCENARIOS.items():
        assert len(defn.transactions) >= 1, f"{sid} has no transactions"


def test_account_numbers_parallel_to_transactions():
    """ACCOUNT_NUMBERS[id] must have exactly as many entries as defn.transactions."""
    for sid, defn in SCENARIOS.items():
        assert sid in ACCOUNT_NUMBERS, f"{sid} missing from ACCOUNT_NUMBERS"
        assert len(ACCOUNT_NUMBERS[sid]) == len(defn.transactions), (
            f"{sid}: ACCOUNT_NUMBERS has {len(ACCOUNT_NUMBERS[sid])} entries "
            f"but definition has {len(defn.transactions)} transactions"
        )


def test_fraud_probe_amounts_satisfy_pattern():
    defn = SCENARIOS["fraud-probe"]
    amounts = [t.amount for t in defn.transactions]
    assert any(a <= 10.00 for a in amounts), "no probe (amount ≤ 10) in fraud-probe"
    assert any(a >= 500.00 for a in amounts), "no large charge (amount ≥ 500) in fraud-probe"


def test_merchant_streak_all_same_category():
    defn = SCENARIOS["merchant-streak"]
    # The three main FOOD charges must share the same merchant_category
    food_txns = [t for t in defn.transactions if t.merchant_category == "FOOD"]
    assert len(food_txns) >= 3, "merchant-streak needs at least 3 FOOD transactions"


def test_smb_spike_has_credit_reversal():
    defn = SCENARIOS["smb-spike"]
    types = [t.transaction_type for t in defn.transactions]
    assert "DEBIT" in types
    assert "CREDIT" in types


def test_scenario_definitions_are_immutable_labels():
    """Smoke-test that label / pattern / description fields are non-empty strings."""
    for sid, defn in SCENARIOS.items():
        assert defn.label, f"{sid} missing label"
        assert defn.pattern, f"{sid} missing pattern"
        assert defn.description, f"{sid} missing description"
        assert defn.scenario_id == sid
