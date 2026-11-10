"""Unit tests for the analytics service orchestration.

Live mode assembles the ``DataAnalytics`` from the CRM snapshot result sets, and
``get_customer_profile`` / ``get_customer_profile_rtce`` map row dicts to
``CustomerProfile`` models. Both paths are pinned here with the provider boundary
stubbed, so no infra is touched.
"""

from __future__ import annotations

from decimal import Decimal

from analytics import service

_SUMMARY = {
    "qscope": "ALL",
    "total_customers": 10,
    "total_accounts": 9,
    "total_balance": Decimal("343671"),
    "total_transactions": 279,
    "total_txn_amount": Decimal("41819"),
    "avg_income": 52000.0,
    "missing_email": 0,
    "missing_phone": 0,
    "complete": 10,
}
_SEG = [
    {"customer_segment": "PRIVATE", "customer_count": 6, "account_balance": Decimal("260601")},
    {"customer_segment": "SMB", "customer_count": 4, "account_balance": Decimal("83070")},
]


def test_get_data_analytics_assembles_from_crm(monkeypatch):
    monkeypatch.setattr(
        service.providers,
        "fetch_crm_result_sets",
        lambda: (_SUMMARY, _SEG, [], [], []),
    )
    r = service.get_data_analytics()
    assert r.source_mode == "live"
    assert r.total_customers == 10
    assert r.row_count == 10
    assert [c.label for c in r.by_segment] == ["PRIVATE", "SMB"]
    assert r.query_ms >= 0


def test_get_customer_profile_maps_row(monkeypatch):
    row = {
        "customer_id": "00000000-0000-0000-0000-678901234568",
        "first_name": "Thomas",
        "last_name": "Brennan",
        "customer_segment": "SMB",
        "account_count": 6,
        "total_balance": "318400.00",
        "txn_count": "512",
        "txn_total": "12345.67",
    }
    monkeypatch.setattr(
        service.providers,
        "get_customer_profile",
        lambda cid: (row, "live") if cid == "00000000-0000-0000-0000-678901234568" else (None, "live"),
    )
    profile = service.get_customer_profile("00000000-0000-0000-0000-678901234568")
    assert profile is not None
    assert profile.source_mode == "live"
    assert profile.first_name == "Thomas"
    assert profile.last_name == "Brennan"
    assert profile.account_count == 6
    assert profile.total_balance == 318400.0
    assert profile.txn_count == 512
    assert profile.query_ms >= 0

    assert service.get_customer_profile("nonexistent") is None


def test_get_customer_profile_rtce_maps_row(monkeypatch):
    row = {
        "customer_id": "00000000-0000-0000-0000-678901234568",
        "first_name": "Thomas",
        "last_name": "Brennan",
        "customer_segment": "SMB",
        "account_count": 6,
        "total_balance": 318400.00,
        "txn_count": 512,
        "txn_total": 12345.67,
    }
    monkeypatch.setattr(
        service.providers,
        "get_customer_profile_rtce",
        lambda cid: (row, "live") if cid == "00000000-0000-0000-0000-678901234568" else (None, "live"),
    )
    profile = service.get_customer_profile_rtce("00000000-0000-0000-0000-678901234568")
    assert profile is not None
    assert profile.source_mode == "live"
    assert profile.first_name == "Thomas"
    assert profile.query_ms >= 0

    assert service.get_customer_profile_rtce("nonexistent") is None
