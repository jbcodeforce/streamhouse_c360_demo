"""Unit tests for the confluent-sql snapshot client (mapping + degradation).

A fake ``confluent_sql.connect`` stands in for the driver, so the connect →
cursor → execute → fetch → close flow and the row/column mapping are exercised
without any network, and the failure-tolerant contract ([] on any problem) is
pinned.
"""

from __future__ import annotations

from types import SimpleNamespace

from analytics import confluent_sql_client
from analytics.confluent_sql_client import ConfluentSqlClient

_SETTINGS = SimpleNamespace(
    FLINK_ORG_ID="org",
    FLINK_ENV_ID="env",
    CLOUD_PROVIDER="aws",
    CLOUD_REGION="us-west-2",
    FLINK_SNAPSHOT_COMPUTE_POOL_ID="lfcp-snapshot",
    FLINK_API_KEY="k",
    FLINK_API_SECRET="s",
    FLINK_DATABASE="db",
    KAFKA_CLUSTER_ID="lkc-1",
)


class _FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows
        self.closed = False
        self.executed = None

    def execute(self, sql):
        self.executed = sql

    def fetchall(self):
        return self._rows

    def close(self):
        self.closed = True


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def test_query_returns_empty_when_a_setting_is_unset():
    settings = SimpleNamespace(**{**_SETTINGS.__dict__, "CLOUD_REGION": None})
    assert ConfluentSqlClient(settings).query("SELECT * FROM t") == []


def test_query_maps_rows_to_dicts(monkeypatch):
    cursor = _FakeCursor(description=[("a",), ("b",)], rows=[(1, 2), (3, 4)])
    conn = _FakeConn(cursor)
    monkeypatch.setattr(
        confluent_sql_client.confluent_sql, "connect", lambda **kw: conn
    )
    rows = ConfluentSqlClient(_SETTINGS).query("SELECT a, b FROM t")
    assert rows == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    assert cursor.executed == "SELECT a, b FROM t"


def test_query_returns_empty_on_exception(monkeypatch):
    def boom(**kw):
        raise RuntimeError("connect failed")

    monkeypatch.setattr(confluent_sql_client.confluent_sql, "connect", boom)
    assert ConfluentSqlClient(_SETTINGS).query("SELECT * FROM t") == []


def test_query_closes_cursor_and_connection(monkeypatch):
    cursor = _FakeCursor(description=[("a",)], rows=[(1,)])
    conn = _FakeConn(cursor)
    monkeypatch.setattr(
        confluent_sql_client.confluent_sql, "connect", lambda **kw: conn
    )
    ConfluentSqlClient(_SETTINGS).query("SELECT a FROM t")
    assert cursor.closed is True
    assert conn.closed is True


def test_query_runs_on_the_snapshot_compute_pool(monkeypatch):
    captured = {}

    def fake_connect(**kw):
        captured.update(kw)
        return _FakeConn(_FakeCursor(description=[("a",)], rows=[(1,)]))

    monkeypatch.setattr(confluent_sql_client.confluent_sql, "connect", fake_connect)
    # A pipeline pool is also configured; it must never be used for snapshot queries.
    settings = SimpleNamespace(**{**_SETTINGS.__dict__, "FLINK_COMPUTE_POOL_ID": "lfcp-c360"})
    ConfluentSqlClient(settings).query("SELECT a FROM t")
    assert captured["compute_pool_id"] == "lfcp-snapshot"


def test_query_does_not_fall_back_to_the_pipeline_pool(monkeypatch):
    def boom(**kw):  # pragma: no cover - must not be called
        raise AssertionError("connect must not be called without the snapshot pool")

    monkeypatch.setattr(confluent_sql_client.confluent_sql, "connect", boom)
    settings = SimpleNamespace(
        **{**_SETTINGS.__dict__, "FLINK_SNAPSHOT_COMPUTE_POOL_ID": None, "FLINK_COMPUTE_POOL_ID": "lfcp-c360"}
    )
    assert ConfluentSqlClient(settings).query("SELECT a FROM t") == []
