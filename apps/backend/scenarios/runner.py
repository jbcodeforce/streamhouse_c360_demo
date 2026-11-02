"""Pure transaction builder for CEP scenarios.

No I/O — deterministic given the same ScenarioDefinition and now.
The runner resolves account_id from account_number using the same
uuid5 derivation as accounts/inventory.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5

from scenarios.models import ScenarioDefinition
from scenarios.registry import ACCOUNT_NUMBERS
from transactions.models import TransactionCreate

# Must match the namespace in accounts/inventory.py exactly.
_ACCOUNT_ID_NAMESPACE = UUID("6ba7b814-9dad-11d1-80b4-00c04fd430c8")


def _account_id_for(account_number: str) -> UUID:
    return uuid5(_ACCOUNT_ID_NAMESPACE, account_number)


def build_transactions(
    defn: ScenarioDefinition,
    now: datetime | None = None,
) -> list[TransactionCreate]:
    """Materialise a scenario into TransactionCreate rows.

    Timestamps are shifted by each entry's offset_seconds relative to *now*
    (defaults to utcnow).  Account IDs are resolved from account_number via the
    same deterministic uuid5 derivation used by accounts/inventory.py.
    """
    now = now or datetime.now(tz=timezone.utc)
    account_numbers = ACCOUNT_NUMBERS[defn.scenario_id]
    result: list[TransactionCreate] = []
    for txn_def, acct_num in zip(defn.transactions, account_numbers, strict=True):
        from datetime import timedelta

        transacted_at = now + timedelta(seconds=txn_def.offset_seconds)
        result.append(
            TransactionCreate(
                account_id=_account_id_for(acct_num),
                customer_id=txn_def.customer_id,
                transaction_type=txn_def.transaction_type,
                amount=txn_def.amount,
                currency=txn_def.currency,
                description=txn_def.description,
                merchant_name=txn_def.merchant_name,
                merchant_category=txn_def.merchant_category,
                channel=txn_def.channel,
                status=txn_def.status,
                transacted_at=transacted_at,
                posted_at=transacted_at,
            )
        )
    return result
