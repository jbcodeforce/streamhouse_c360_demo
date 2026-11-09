"""In-memory accounts inventory backed by the seed CSV (infra-free)."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from uuid import uuid4

from accounts import inventory
from accounts.models import Account

_HEADER = "customer_id,account_number,account_type,currency,balance,credit_limit,opened_date,closed_date,status\n"
_ROW = "a1b2c3d4-e5f6-7890-abcd-ef1234567890,CHK-1,CHECKING,USD,472.66,,2018-01-31,,ACTIVE\n"


def _account(number: str) -> Account:
    now = datetime.now(tz=timezone.utc)
    return Account(
        account_id=uuid4(), customer_id=uuid4(), account_number=number,
        account_type="SAVINGS", currency="USD", balance=1.0, credit_limit=None,
        opened_date=date(2020, 1, 1), closed_date=None, status="ACTIVE",
        created_at=now, updated_at=now,
    )


def test_load_parses_seed_csv():
    # Reads the session's throwaway copy of the seed (see conftest isolation).
    with inventory._csv_path().open(newline="", encoding="utf-8") as fh:
        expected = sum(1 for _ in csv.DictReader(fh))
    accounts = inventory.load()
    assert len(accounts) == expected
    first = accounts[0]
    assert first.account_number == "CHK-39958838"
    assert first.account_type == "CHECKING"
    assert first.balance == 472.66
    assert first.credit_limit == 2000.0
    assert first.account_id is not None          # server field generated at load
    assert first.created_at is not None


def test_account_id_is_stable_across_loads():
    # account_id is derived from account_number, so it must not change between
    # restarts — otherwise transaction FKs break on re-seed. Regression guard.
    first = {a.account_number: a.account_id for a in inventory.load()}
    second = {a.account_number: a.account_id for a in inventory.load()}
    assert first == second


def test_create_appends_and_persists(tmp_path, monkeypatch):
    csv_path = tmp_path / "accounts.csv"
    csv_path.write_text(_HEADER + _ROW, encoding="utf-8")
    monkeypatch.setenv("ACCOUNTS_CSV_PATH", str(csv_path))
    inventory.load()
    assert len(inventory.list_all()) == 1

    created = inventory.create(_account("SAV-9"))
    assert len(inventory.list_all()) == 2
    assert inventory.get_by_id(created.account_id) is created
    # persisted (2 data rows) and keeps the 9-column schema (no account_id col)
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + 2
    assert lines[0].split(",")[0] == "customer_id"
    assert "account_id" not in lines[0]


def test_update_replaces(tmp_path, monkeypatch):
    csv_path = tmp_path / "accounts.csv"
    csv_path.write_text(_HEADER + _ROW, encoding="utf-8")
    monkeypatch.setenv("ACCOUNTS_CSV_PATH", str(csv_path))
    [existing] = inventory.load()
    changed = existing.model_copy(update={"status": "CLOSED"})
    inventory.update(changed)
    assert inventory.get_by_id(existing.account_id).status == "CLOSED"


def test_delete_removes(tmp_path, monkeypatch):
    csv_path = tmp_path / "accounts.csv"
    csv_path.write_text(_HEADER + _ROW, encoding="utf-8")
    monkeypatch.setenv("ACCOUNTS_CSV_PATH", str(csv_path))
    [existing] = inventory.load()
    assert inventory.delete_by_id(existing.account_id) is True
    assert inventory.list_all() == []
    assert inventory.delete_by_id(existing.account_id) is False
