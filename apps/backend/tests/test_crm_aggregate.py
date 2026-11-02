"""Unit tests for the live CRM aggregate assembler (pure, no I/O).

``assemble`` folds the five ``fct_crm_*`` snapshot result sets into a
``DataAnalytics``. It must match ``aggregate()`` where both run: Decimal→float
coercion, derived per-customer average, null→"Unknown" relabel, (-count, label)
ordering, and the by_country top-8 + "Other" fold.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from analytics.crm_aggregate import assemble

SUMMARY = {
    "qscope": "ALL",
    "total_customers": 10,
    "total_accounts": 9,
    "total_balance": Decimal("343671"),
    "total_transactions": 279,
    "total_txn_amount": Decimal("41819"),
    "avg_age": 41.8,
    "missing_email": 0,
    "missing_phone": 0,
    "complete": 10,
}
SEG = [
    {"customer_segment": "PRIVATE", "customer_count": 6, "total_balance": Decimal("260601")},
    {"customer_segment": "SMB", "customer_count": 4, "total_balance": Decimal("83070")},
]


def test_scalars_and_derived_average():
    r = assemble(SUMMARY, SEG, [], [], [], source_mode="live")
    assert r.total_customers == 10
    assert r.row_count == 10
    assert r.total_accounts == 9
    assert r.total_transactions == 279
    assert r.total_balance == pytest.approx(343671.0)
    assert r.total_txn_amount == pytest.approx(41819.0)
    assert r.avg_age == pytest.approx(41.8)
    assert r.avg_balance_per_customer == pytest.approx(34367.1)
    assert r.source_mode == "live"
    assert r.data_quality.complete == 10


def test_segment_feeds_both_count_and_balance_series():
    r = assemble(SUMMARY, SEG, [], [], [], source_mode="live")
    assert [(c.label, c.count) for c in r.by_segment] == [("PRIVATE", 6), ("SMB", 4)]
    assert [(c.label, c.value) for c in r.balance_by_segment] == [
        ("PRIVATE", pytest.approx(260601.0)),
        ("SMB", pytest.approx(83070.0)),
    ]


def test_distribution_ordered_and_tie_broken_by_label():
    gender = [{"gender": "M", "gender_count": 5}, {"gender": "F", "gender_count": 5}]
    r = assemble(SUMMARY, SEG, [], gender, [], source_mode="live")
    # Tie at 5 -> alphabetical by label for determinism.
    assert [(c.label, c.count) for c in r.by_gender] == [("F", 5), ("M", 5)]


def test_null_category_relabelled_unknown():
    gender = [{"gender": None, "gender_count": 3}]
    r = assemble(SUMMARY, SEG, [], gender, [], source_mode="live")
    assert r.by_gender[0].label == "Unknown"


def test_generation_distribution_from_its_count_column():
    gen = [
        {"generation_segment": "Millennial", "generation_count": 5},
        {"generation_segment": "Gen X", "generation_count": 4},
    ]
    r = assemble(SUMMARY, SEG, gen, [], [], source_mode="live")
    assert [(c.label, c.count) for c in r.by_generation] == [("Millennial", 5), ("Gen X", 4)]


def test_country_top_n_folds_tail_into_other():
    country = [{"country": f"C{i}", "country_count": 1} for i in range(12)]
    r = assemble(SUMMARY, SEG, [], [], country, source_mode="live")
    assert r.by_country[-1].label == "Other"
    assert len(r.by_country) == 9
    assert r.by_country[-1].count == 4


def test_empty_summary_is_safe():
    r = assemble(None, [], [], [], [], source_mode="live")
    assert r.row_count == 0
    assert r.total_customers == 0
    assert r.total_balance == 0
    assert r.avg_age is None
    assert r.avg_balance_per_customer is None
    assert r.by_segment == []
    assert r.balance_by_segment == []
    assert r.data_quality.complete == 0


def test_non_numeric_avg_age_degrades_to_none_without_raising():
    # The live path is never wrapped, so a bad avg_age must not raise (→ HTTP 500).
    bad = {**SUMMARY, "avg_age": "n/a"}
    r = assemble(bad, SEG, [], [], [], source_mode="live")
    assert r.avg_age is None
    assert r.total_customers == 10  # the rest of the payload still assembles
