"""Unit tests for the analytics service orchestration (mode branch).

Mock mode folds the fixture through ``aggregate()``; live mode assembles the
``DataAnalytics`` from the CRM snapshot result sets. Both branches are pinned
here with the provider boundary stubbed, so no infra is touched.
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
    "avg_age": 41.8,
    "missing_email": 0,
    "missing_phone": 0,
    "complete": 10,
}
_SEG = [
    {"customer_segment": "PRIVATE", "customer_count": 6, "total_balance": Decimal("260601")},
    {"customer_segment": "SMB", "customer_count": 4, "total_balance": Decimal("83070")},
]


def test_live_path_assembles_from_crm(monkeypatch):
    monkeypatch.setattr(service.providers, "_mode", lambda: "live")
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


def test_mock_path_folds_fixture(monkeypatch):
    monkeypatch.setattr(service.providers, "_mode", lambda: "mock")
    r = service.get_data_analytics()
    assert r.source_mode == "mock"
    assert r.total_customers == 10
    assert r.row_count == 10
