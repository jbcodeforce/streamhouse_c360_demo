"""Unit tests for the concurrent CRM snapshot fetch.

A fake ``client_factory`` records the SQL and returns canned per-table rows, so
the five-query dispatch, the summary single-row extraction, and worker-error
isolation are exercised without any driver or network.
"""

from __future__ import annotations

from analytics.providers import fetch_crm_result_sets

CANNED = {
    "fct_crm_summary": [{"qscope": "ALL", "total_customers": 10}],
    "fct_crm_by_segment": [{"customer_segment": "PRIVATE", "customer_count": 6}],
    "fct_crm_by_generation": [{"generation_segment": "Millennial", "generation_count": 5}],
    "fct_crm_by_gender": [{"gender": "F", "gender_count": 5}],
    "fct_crm_by_country": [{"country": "US", "country_count": 10}],
}


def _table_of(sql: str) -> str:
    return sql.split("FROM ", 1)[1].strip()


class _FakeClient:
    def __init__(self, recorded: list[str]):
        self._recorded = recorded

    def query(self, sql: str) -> list[dict]:
        self._recorded.append(sql)
        return CANNED.get(_table_of(sql), [])


def _factory(recorded):
    return lambda: _FakeClient(recorded)


def test_fetch_dispatches_one_select_per_table():
    recorded: list[str] = []
    summary, seg, gen, gender, country = fetch_crm_result_sets(client_factory=_factory(recorded))
    assert summary == {"qscope": "ALL", "total_customers": 10}
    assert seg == [{"customer_segment": "PRIVATE", "customer_count": 6}]
    assert gen == [{"generation_segment": "Millennial", "generation_count": 5}]
    assert gender == [{"gender": "F", "gender_count": 5}]
    assert country == [{"country": "US", "country_count": 10}]
    assert set(recorded) == {f"SELECT * FROM {t}" for t in CANNED}


def test_empty_summary_yields_none_slot():
    class _EmptySummary:
        def query(self, sql):
            return [] if _table_of(sql) == "fct_crm_summary" else [{"x": 1}]

    summary, *_ = fetch_crm_result_sets(client_factory=lambda: _EmptySummary())
    assert summary is None


def test_one_table_raising_is_isolated():
    class _CountryBoom:
        def query(self, sql):
            table = _table_of(sql)
            if table == "fct_crm_by_country":
                raise RuntimeError("boom")
            return CANNED.get(table, [])

    summary, seg, gen, gender, country = fetch_crm_result_sets(client_factory=lambda: _CountryBoom())
    assert country == []
    assert summary is not None
    assert seg == [{"customer_segment": "PRIVATE", "customer_count": 6}]
