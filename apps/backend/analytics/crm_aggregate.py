"""Fold the five ``fct_crm_*`` snapshot result sets into a ``DataAnalytics``.

Pure function, no I/O. Each ``fct_crm_*`` table is already aggregated in
Flink, so this only maps and orders the pre-computed rows.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from analytics.models import (
    CategoryCount,
    CategoryValue,
    DataAnalytics,
    DataQuality,
)


# Top-N cap for the geography breakdown so a long tail of countries doesn't
# overrun the chart; everything past the cap folds into "Other".
_COUNTRY_TOP_N = 8


def _num(value: object) -> float:
    """Coerce a possibly-None / string-decimal cell to float; blanks → 0.0."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _avg_age(value: object) -> float | None:
    """Coerce the summary's ``avg_age`` to a rounded float.

    ``None`` when absent/blank or non-numeric — never raises, so a bad cell can't
    turn the (unwrapped) live assemble path into an HTTP 500.
    """
    if value in (None, ""):
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _counts(rows: list[dict], label_field: str, count_field: str) -> list[CategoryCount]:
    """Map pre-aggregated rows to ordered counts: null→"Unknown", (-count, label)."""
    agg: dict[str, int] = defaultdict(int)
    for r in rows:
        label = str(r.get(label_field) or "Unknown")
        agg[label] += int(_num(r.get(count_field)))
    ordered = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
    return [CategoryCount(label=label, count=count) for label, count in ordered]


def assemble(
    summary_row: dict | None,
    by_segment: list[dict],
    by_generation: list[dict],
    by_gender: list[dict],
    by_country: list[dict],
    *,
    source_mode: str,
    query_ms: float = 0.0,
) -> DataAnalytics:
    """Fold the CRM snapshot result sets into the dashboard payload.

    Safe on an empty/missing summary: totals are 0, averages ``None``, and every
    distribution an empty list, so the UI renders an empty state.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = summary_row or {}

    total_customers = int(_num(s.get("total_customers")))
    total_balance = round(_num(s.get("total_balance")), 2)

    avg_age = _avg_age(s.get("avg_age"))
    avg_balance = round(total_balance / total_customers, 2) if total_customers else None

    # Segment table feeds both the count series and the balance series.
    balance_map: dict[str, float] = defaultdict(float)
    for r in by_segment:
        balance_map[str(r.get("customer_segment") or "Unknown")] += _num(r.get("total_balance"))
    balance_by_segment = [
        CategoryValue(label=label, value=round(value, 2))
        for label, value in sorted(balance_map.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    country = _counts(by_country, "country", "country_count")
    if len(country) > _COUNTRY_TOP_N:
        head = country[:_COUNTRY_TOP_N]
        other = sum(c.count for c in country[_COUNTRY_TOP_N:])
        head.append(CategoryCount(label="Other", count=other))
        country = head

    return DataAnalytics(
        source_mode=source_mode,
        generated_at=now,
        query_ms=query_ms,
        row_count=total_customers,
        total_customers=total_customers,
        total_accounts=int(_num(s.get("total_accounts"))),
        total_balance=total_balance,
        total_transactions=int(_num(s.get("total_transactions"))),
        total_txn_amount=round(_num(s.get("total_txn_amount")), 2),
        avg_balance_per_customer=avg_balance,
        avg_age=avg_age,
        data_quality=DataQuality(
            complete=int(_num(s.get("complete"))),
            missing_email=int(_num(s.get("missing_email"))),
            missing_phone=int(_num(s.get("missing_phone"))),
        ),
        by_segment=_counts(by_segment, "customer_segment", "customer_count"),
        by_generation=_counts(by_generation, "generation_segment", "generation_count"),
        by_gender=_counts(by_gender, "gender", "gender_count"),
        by_country=country,
        balance_by_segment=balance_by_segment,
    )
