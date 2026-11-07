"""cards.inventory — the seed CSV links one debit card to each CHECKING account."""

from __future__ import annotations

from accounts import inventory as accounts_inventory
from cards import inventory as cards_inventory


def test_one_debit_card_per_checking_account():
    accounts = accounts_inventory.load()
    cards = cards_inventory.load()

    checking_ids = {a.account_id for a in accounts if a.account_type == "CHECKING"}
    card_account_ids = [c.account_id for c in cards]

    assert set(card_account_ids) == checking_ids
    assert len(card_account_ids) == len(checking_ids)  # exactly one each
    assert all(c.card_type == "DEBIT" for c in cards)
    assert all(c.credit_limit is None for c in cards)


def test_card_ids_are_stable_across_loads():
    first = {c.card_number: c.card_id for c in cards_inventory.load()}
    second = {c.card_number: c.card_id for c in cards_inventory.load()}
    assert first == second
