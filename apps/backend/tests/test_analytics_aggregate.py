"""Unit tests for the C360 analytics aggregation (pure, no I/O)."""

from __future__ import annotations

import pytest

from analytics.aggregate import mock_aggregate
from analytics.mock_data import PROFILE_SNAPSHOT


@pytest.fixture
def result():
    return mock_aggregate(PROFILE_SNAPSHOT, source_mode="mock")


def test_headline_totals(result):
    assert result.row_count == 10
    assert result.total_customers == 10
    assert result.total_accounts == 31
    assert result.total_transactions == 2146
    assert result.total_balance == pytest.approx(932001.50)
    assert result.total_txn_amount == pytest.approx(3124240.00)


def test_averages(result):
    assert result.avg_age == pytest.approx(40.8)
    assert result.avg_balance_per_customer == pytest.approx(93200.15)


def test_data_quality_rollup(result):
    assert result.data_quality.missing_phone == 2
    assert result.data_quality.missing_email == 0
    assert result.data_quality.complete == 8


def test_segment_distribution_ordered_largest_first(result):
    assert [(c.label, c.count) for c in result.by_segment] == [("PRIVATE", 6), ("SMB", 4)]


def test_generation_distribution(result):
    assert [(c.label, c.count) for c in result.by_generation] == [
        ("Millennial", 5),
        ("Gen X", 4),
        ("Boomer+", 1),
    ]


def test_gender_tie_broken_by_label(result):
    # Both genders tie at 5; ties break alphabetically for determinism.
    assert [(c.label, c.count) for c in result.by_gender] == [("F", 5), ("M", 5)]


def test_balance_by_segment_ordered_by_value(result):
    pairs = [(c.label, c.value) for c in result.balance_by_segment]
    assert pairs[0][0] == "SMB"
    assert pairs[0][1] == pytest.approx(743850.00)
    assert pairs[1][0] == "PRIVATE"
    assert pairs[1][1] == pytest.approx(188151.50)


def test_empty_snapshot_is_safe():
    r = mock_aggregate([], source_mode="live")
    assert r.row_count == 0
    assert r.total_customers == 0
    assert r.total_balance == 0
    assert r.avg_age is None
    assert r.avg_balance_per_customer is None
    assert r.by_segment == []
    assert r.data_quality.complete == 0


def test_country_top_n_folds_tail_into_other():
    rows = [{"country": f"C{i}"} for i in range(12)]
    r = mock_aggregate(rows, source_mode="mock")
    labels = [c.label for c in r.by_country]
    assert labels[-1] == "Other"
    # 8 head countries + the Other bucket.
    assert len(r.by_country) == 9
    assert r.by_country[-1].count == 4
