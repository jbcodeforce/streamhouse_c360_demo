"""Orchestration for the C360 analytics dashboard.

Thin layer between the API router and the ``providers``/``crm_aggregate`` modules:
the aggregate dashboard folds CRM snapshots; the customer lookup fetches one
profile via a ``WHERE customer_id = …`` query. Name-to-id resolution lives in
the operational customer service (the system of record for identity), not here.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from analytics import crm_aggregate, providers
from analytics.models import CustomerProfile, DataAnalytics

_T = TypeVar("_T")


def _timed(call: Callable[[], _T]) -> tuple[_T, float]:
    """Run ``call`` and return ``(result, elapsed_ms)``.

    Times only the query itself (the provider call that hits Confluent), not any
    downstream Python work, so the number the UI shows is the query's own latency.
    """
    start = time.perf_counter()
    result = call()
    return result, round((time.perf_counter() - start) * 1000, 1)


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def get_data_analytics() -> DataAnalytics:
    """Dashboard aggregates: reads the CRM data products and assembles the payload.

    Runs the five ``fct_crm_*`` snapshot queries concurrently and assembles the
    payload from pre-aggregated summary rows.
    """
    result_sets, query_ms = _timed(providers.fetch_crm_result_sets)
    return crm_aggregate.assemble(*result_sets, source_mode="live", query_ms=query_ms)


def get_customer_profile(customer_id: str) -> CustomerProfile | None:
    (row, source_mode), query_ms = _timed(lambda: providers.get_customer_profile(customer_id))
    return _to_profile(row, source_mode, query_ms)


def get_customer_profile_rtce(customer_id: str) -> CustomerProfile | None:
    (row, source_mode), query_ms = _timed(lambda: providers.get_customer_profile_rtce(customer_id))
    return _to_profile(row, source_mode, query_ms)


def _to_profile(row: dict | None, source_mode: str, query_ms: float) -> CustomerProfile | None:
    if row is None:
        return None
    return CustomerProfile(
        source_mode=source_mode,
        query_ms=query_ms,
        customer_id=str(row.get("customer_id")),
        first_name=row.get("first_name"),
        last_name=row.get("last_name"),
        customer_segment=row.get("customer_segment"),
        generation_segment=row.get("generation_segment"),
        gender=row.get("gender"),
        age_years=_to_int(row.get("age_years")),
        city=row.get("city"),
        state=row.get("state"),
        country=row.get("country"),
        customer_since=(str(row["customer_since"]) if row.get("customer_since") else None),
        days_since_registration=_to_int(row.get("days_since_registration")),
        missing_email_flag=_to_int(row.get("missing_email_flag")),
        missing_phone_flag=_to_int(row.get("missing_phone_flag")),
        account_count=_to_int(row.get("account_count")) or 0,
        total_balance=_to_float(row.get("total_balance")),
        txn_count=_to_int(row.get("txn_count")) or 0,
        txn_total=_to_float(row.get("txn_total")),
    )
