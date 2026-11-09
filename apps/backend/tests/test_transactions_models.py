"""Transaction model defaults and optionality."""

from __future__ import annotations

from transactions.models import Transaction, TransactionCreate


def test_create_applies_defaults():
    t = TransactionCreate(
        account_id="11111111-1111-1111-1111-111111111111",
        customer_id="22222222-2222-2222-2222-222222222222",
        transaction_type="CREDIT",
        amount=10.5,
    )
    assert t.currency == "USD"
    assert t.status == "COMPLETED"
    assert t.transacted_at is not None
    assert t.description is None
    assert t.posted_at is None


def test_transacted_at_default_is_dynamic():
    field = TransactionCreate.model_fields["transacted_at"]
    assert field.default_factory is not None


def test_transaction_has_server_fields_and_no_updated_at():
    fields = set(Transaction.model_fields)
    assert {"transaction_id", "created_at"} <= fields
    assert "updated_at" not in fields


def test_card_only_transaction_is_valid():
    t = TransactionCreate(
        customer_id="22222222-2222-2222-2222-222222222222",
        card_id="33333333-3333-3333-3333-333333333333",
        transaction_type="DEBIT",
        amount=5,
    )
    assert t.account_id is None


def test_requires_account_or_card():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TransactionCreate(
            customer_id="22222222-2222-2222-2222-222222222222",
            transaction_type="DEBIT",
            amount=5,
        )
