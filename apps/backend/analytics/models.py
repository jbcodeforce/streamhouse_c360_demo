"""Pydantic models for the C360 analytics dashboard.

The dashboard reads a single snapshot of ``fct_c360_profile`` and renders it as
KPI tiles plus a handful of single-series distributions. ``DataAnalytics`` is
the whole response: headline totals, averages, a data-quality rollup, and the
category breakdowns the frontend draws as bar charts.
"""

from __future__ import annotations

from pydantic import BaseModel


class CategoryCount(BaseModel):
    """One bar in a count distribution (e.g. customers per segment)."""

    label: str
    count: int


class CategoryValue(BaseModel):
    """One bar in a value distribution (e.g. total balance per segment)."""

    label: str
    value: float


class DataQuality(BaseModel):
    """Completeness rollup derived from the ``missing_*_flag`` columns."""

    complete: int
    missing_email: int
    missing_phone: int


class DataAnalytics(BaseModel):
    """Full dashboard payload for one snapshot of ``fct_c360_profile``.

    ``source_mode`` is "live" so the UI can label where the snapshot
    came from; ``row_count`` is how many profile rows the snapshot returned
    (0 when a live query is unconfigured or fails — the dashboard then shows an
    empty state rather than erroring).
    """

    source_mode: str
    generated_at: str
    row_count: int
    # Wall-clock time the snapshot query itself took (backend-measured), ms.
    query_ms: float = 0.0

    # Headline totals
    total_customers: int
    total_accounts: int
    total_balance: float
    total_transactions: int
    total_txn_amount: float

    # Averages (None when there are no rows to average)
    avg_balance_per_customer: float | None = None
    avg_income: float | None = None

    data_quality: DataQuality

    # Single-series distributions, each ordered largest-first
    by_segment: list[CategoryCount]
    by_generation: list[CategoryCount]
    by_gender: list[CategoryCount]
    by_country: list[CategoryCount]
    balance_by_segment: list[CategoryValue]


class CustomerProfile(BaseModel):
    """Per-customer metrics from a ``WHERE customer_id = …`` snapshot query."""

    source_mode: str
    # Wall-clock time the lookup query took (backend-measured), ms.
    query_ms: float = 0.0
    customer_id: str
    first_name: str | None = None
    last_name: str | None = None
    customer_segment: str | None = None
    generation_segment: str | None = None
    gender: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    customer_since: str | None = None
    days_since_registration: int | None = None
    missing_email_flag: int | None = None
    missing_phone_flag: int | None = None
    account_count: int = 0
    total_balance: float = 0.0
    txn_count: int = 0
    txn_total: float = 0.0
