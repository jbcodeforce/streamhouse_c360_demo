"""Seed-source for transactions, backed by a CSV keyed by account_number.

The CSV has no transaction_id/account_id (both server/derived). ``load`` takes
the already-loaded accounts, resolves each row's account_number to the real
account_id/customer_id, and generates transaction_id/created_at. Rows whose
account_number is unknown are skipped.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

from accounts.inventory import _ACCOUNT_ID_NAMESPACE, _account_id_for
from transactions.models import Transaction

_CSV_PATH = Path(__file__).parent / "data" / "transactions.csv"

_FIELDNAMES = [
    "transaction_id",
    "account_id",
    "customer_id",
    "transaction_type",
    "amount",
    "currency",
    "description",
    "merchant_name",
    "merchant_category",
    "channel",
    "status",
    "transacted_at",
    "posted_at",
    "created_at",
    "card_id",
    "use_chip",
    "merchant_city",
    "merchant_state",
    "zip",
]

_transactions: list[Transaction] = []


def _csv_path() -> Path:
    """Resolve the CSV path, honouring the TRANSACTIONS_CSV_PATH override.

    Tests point this at a throwaway copy of the seed data so they never mutate
    the committed seed file.
    """
    override = os.getenv("TRANSACTIONS_CSV_PATH")
    return Path(override) if override else _CSV_PATH


def _row_to_transaction(row: dict) -> Transaction:
    """Convert a CSV row dict to a Transaction, treating empty strings as None.

    Seed rows carry ``account_number`` instead of ``account_id`` and have no
    ``transaction_id``/``created_at``. ``account_id`` is derived from the
    account number (same scheme as the accounts inventory) and
    ``transaction_id`` is deterministic, so Postgres and Kafka agree on ids
    across restarts.
    """
    cleaned = {k: (v if v != "" else None) for k, v in row.items()}
    account_number = cleaned.pop("account_number", None)
    if account_number is not None:
        cleaned.setdefault("account_id", _account_id_for(account_number))
    if not cleaned.get("transaction_id"):
        key = (
            f"{account_number}|{cleaned.get('transacted_at')}|"
            f"{cleaned.get('transaction_type')}|{cleaned.get('amount')}|"
            f"{cleaned.get('merchant_name')}"
        )
        if account_number is None:  # card-only row: keep ids distinct per card
            key += f"|{cleaned.get('card_id')}"
        cleaned["transaction_id"] = str(uuid5(_ACCOUNT_ID_NAMESPACE, key))
    if not cleaned.get("created_at"):
        cleaned["created_at"] = datetime.now(tz=timezone.utc)
    return Transaction.model_validate(cleaned)


def _transaction_to_row(txn: Transaction) -> dict:
    """Serialise a Transaction to a CSV row dict."""
    return {
        "transaction_id": str(txn.transaction_id),
        "account_id": str(txn.account_id) if txn.account_id else "",
        "customer_id": str(txn.customer_id),
        "transaction_type": txn.transaction_type,
        "amount": txn.amount,
        "currency": txn.currency,
        "description": txn.description or "",
        "merchant_name": txn.merchant_name or "",
        "merchant_category": txn.merchant_category or "",
        "channel": txn.channel or "",
        "status": txn.status,
        "transacted_at": txn.transacted_at.isoformat(),
        "posted_at": txn.posted_at.isoformat() if txn.posted_at else "",
        "created_at": txn.created_at.isoformat(),
        "card_id": str(txn.card_id) if txn.card_id else "",
        "use_chip": txn.use_chip or "",
        "merchant_city": txn.merchant_city or "",
        "merchant_state": txn.merchant_state or "",
        "zip": txn.zip or "",
    }


def load() -> list[Transaction]:
    """Read the CSV into the in-memory cache and return it."""
    global _transactions
    with _csv_path().open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        _transactions=[_row_to_transaction(row) for row in reader]
    return _transactions


def list_all() -> list[Transaction]:
    """Return all transactions from the in-memory cache."""
    return _transactions


def get_by_id(transaction_id: UUID) -> Transaction | None:
    """Return the transaction with the given ID, or None if not found."""
    for txn in _transactions:
        if txn.transaction_id == transaction_id:
            return txn
    return None


def create(txn: Transaction) -> Transaction:
    """Append a new transaction to the in-memory cache and persist to CSV."""
    _transactions.append(txn)
    with _csv_path().open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        writer.writerow(_transaction_to_row(txn))
    return txn


def update(txn: Transaction) -> Transaction:
    """Replace an existing transaction in the cache and rewrite the CSV."""
    for i, existing in enumerate(_transactions):
        if existing.transaction_id == txn.transaction_id:
            _transactions[i] = txn
            break
    _rewrite_csv()
    return txn


def delete_by_id(transaction_id: UUID) -> bool:
    """Remove a transaction from the cache and rewrite the CSV. Returns True if found."""
    global _transactions
    before = len(_transactions)
    _transactions = [t for t in _transactions if t.transaction_id != transaction_id]
    if len(_transactions) == before:
        return False
    _rewrite_csv()
    return True


def _rewrite_csv() -> None:
    """Rewrite the entire CSV from the current in-memory cache."""
    with _csv_path().open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for txn in _transactions:
            writer.writerow(_transaction_to_row(txn))
