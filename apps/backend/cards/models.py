from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CardCreate(BaseModel):
    account_id: UUID
    card_brand: str  # VISA, MASTERCARD, ...
    card_type: str  # DEBIT, CREDIT
    card_number: str
    expires: date
    has_chip: bool = True
    credit_limit: Decimal | None = Field(default=None, ge=0)  # NULL for debit cards


class Card(CardCreate):
    model_config = ConfigDict(from_attributes=True)

    card_id: UUID
    created_at: datetime
    updated_at: datetime
