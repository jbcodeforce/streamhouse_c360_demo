"""Pydantic models for the CEP scenario system."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from transactions.models import Transaction


class ScenarioTransaction(BaseModel):
    """One scripted transaction within a scenario definition."""

    account_id: UUID
    customer_id: UUID
    transaction_type: str       # DEBIT | CREDIT
    amount: float
    currency: str = "USD"
    description: str
    merchant_name: str
    merchant_category: str
    channel: str
    status: str = "COMPLETED"
    offset_seconds: int         # seconds after scenario start; runner adds to now


class ScenarioDefinition(BaseModel):
    """A fully scripted transaction sequence that fires a MATCH_RECOGNIZE pattern."""

    scenario_id: str            # e.g. "fraud-probe"
    pattern: str                # Flink table name, e.g. "fct_fraud_probe"
    label: str                  # human label for the UI
    description: str
    transactions: list[ScenarioTransaction]


class ScenarioResult(BaseModel):
    """Returned by POST /scenarios/{id}/run after the sequence is injected."""

    scenario_id: str
    pattern: str
    label: str
    triggered_at: datetime
    transactions: list[Transaction]  # actual Transaction rows after insert
