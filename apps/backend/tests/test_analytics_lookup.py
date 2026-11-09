"""Unit tests for the by-id profile providers: SQL building, escaping, and
row resolution. (Name-to-id search now lives in the customer
service, so the analytics providers only serve by-id profile lookups.)"""

from __future__ import annotations

from analytics import providers


# --- SQL building & escaping ---------------------------------------------

def test_sql_str_doubles_single_quotes():
    assert providers._sql_str("O'Brien") == "'O''Brien'"


def test_profile_sql_filters_by_equality_without_limit():
    sql = providers._profile_sql("00000000-0000-0000-0000-678901234568")
    assert "WHERE customer_id = '00000000-0000-0000-0000-678901234568'" in sql
    # No LIMIT: confluent-sql snapshot mode returns the single current-state row
    # for the key, so there is nothing to truncate.
    assert "LIMIT" not in sql


# --- ConfluentSqlClient-based resolution ----------------------------------

def test_get_customer_profile_unknown_id_returns_none(monkeypatch):
    monkeypatch.setattr(providers.ConfluentSqlClient, "query", lambda self, sql: [])
    row, mode = providers.get_customer_profile("00000000-0000-0000-0000-000000000000")
    assert row is None
    assert mode == "live"


def test_get_customer_profile_rejects_malformed_id_without_query(monkeypatch):
    # A malformed id must never reach the client (it would build a SQL literal).
    def boom(self, sql):  # pragma: no cover - must not be called
        raise AssertionError("client.query should not be called for a malformed id")

    monkeypatch.setattr(providers.ConfluentSqlClient, "query", boom)
    assert providers.get_customer_profile("'; DROP TABLE x; --") == (None, "live")


def test_get_customer_profile_live_delegates_to_client(monkeypatch):
    captured = {}

    def fake_query(self, sql):
        captured["sql"] = sql
        return [{"customer_id": "abc-123", "first_name": "Ada", "last_name": "Lovelace"}]

    monkeypatch.setattr(providers.ConfluentSqlClient, "query", fake_query)
    row, mode = providers.get_customer_profile("abc-123")
    assert mode == "live"
    assert row["first_name"] == "Ada"
    assert "WHERE customer_id = 'abc-123'" in captured["sql"]


# --- RTCE / Lightning provider variant ------------------------------------

def test_rtce_profile_unknown_id_returns_none(monkeypatch):
    monkeypatch.setattr(providers.LightningClient, "query", lambda self, sql, cols, max_rows: [])
    row, mode = providers.get_customer_profile_rtce("00000000-0000-0000-0000-000000000000")
    assert row is None
    assert mode == "live"


def test_rtce_profile_rejects_malformed_id():
    assert providers.get_customer_profile_rtce("'; DROP TABLE x; --") == (None, "live")


def test_rtce_profile_live_delegates_to_lightning(monkeypatch):
    def fake_query(self, sql, fallback_columns, max_rows):
        assert "WHERE customer_id = 'abc-123'" in sql
        return [{"customer_id": "abc-123", "txn_count": 43}]

    monkeypatch.setattr(providers.LightningClient, "query", fake_query)
    row, mode = providers.get_customer_profile_rtce("abc-123")
    assert mode == "live"
    assert row == {"customer_id": "abc-123", "txn_count": 43}
