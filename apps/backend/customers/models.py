from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CustomerCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    date_of_birth: datetime | None = None
    gender: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str = "US"
    customer_since: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    segment: str | None = None
    status: str = "ACTIVE"
    per_capita_income: Decimal | None = Field(default=None, ge=0)
    retirement_age: int | None = Field(default=None, ge=0, le=120)


class CustomerUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    date_of_birth: datetime | None = None
    gender: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    customer_since: datetime | None = None
    segment: str | None = None
    status: str | None = None
    per_capita_income: Decimal | None = Field(default=None, ge=0)
    retirement_age: int | None = Field(default=None, ge=0, le=120)


class Customer(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    customer_id: UUID
    created_at: datetime
    updated_at: datetime
