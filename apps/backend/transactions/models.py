from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class TransactionCreate(BaseModel):
    # A transaction targets an account, a card, or both (card-only transactions
    # have no account number).
    account_id: UUID | None = None
    customer_id: UUID
    transaction_type: str
    amount: float
    currency: str = "USD"
    description: str | None = None
    merchant_name: str | None = None
    merchant_category: str | None = None
    channel: str | None = None
    status: str = "COMPLETED"
    transacted_at: datetime = Field(default_factory=_now)
    posted_at: datetime | None = None
    card_id: UUID | None = None
    use_chip: str | None = None  # e.g. "Swipe Transaction", "Chip Transaction", "Online Transaction"
    merchant_city: str | None = None
    merchant_state: str | None = None
    zip: str | None = None

    @model_validator(mode="after")
    def _require_account_or_card(self) -> "TransactionCreate":
        if self.account_id is None and self.card_id is None:
            raise ValueError("a transaction requires an account_id or a card_id")
        return self


class Transaction(TransactionCreate):
    model_config = ConfigDict(from_attributes=True)
    transaction_id: UUID
    created_at: datetime
