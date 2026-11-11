"""Tests for the live (best-effort Confluent REST) status/metrics provider.

httpx is mocked at the client boundary: these tests inject a fake/raising
object in place of ``confluent_client.ConfluentClient`` into
``providers.LiveProvider(client=...)``, so no real network call is ever
made.
"""

from __future__ import annotations

import types
from datetime import date, datetime, timezone

import httpx

from data_products import confluent_client, descriptor, providers
from data_products.models import Graph, GraphNode


class _FakeClient:
    """Stand-in for ``confluent_client.ConfluentClient`` (all 4 Protocol methods)."""

    def __init__(
        self,
        phases: dict[str, str] | None = None,
        metrics: dict | None = None,
        mt_tables: dict[str, dict] | None = None,
        mt_metrics: dict | None = None,
        statements: dict[str, dict] | None = None,
        pool_costs: dict[str, float] | None = None,
        pool_cfu: dict[str, float] | None = None,
    ) -> None:
        self._phases = phases or {}
        self._metrics = metrics or {}
        self._mt_tables = mt_tables or {}
        self._mt_metrics = mt_metrics or {}
        self._statements = statements or {}
        self._pool_costs = pool_costs or {}
        self._pool_cfu = pool_cfu or {}

    def list_statement_phases(self) -> dict[str, str]:
        return dict(self._phases)

    def list_statements(self) -> dict[str, dict]:
        return {name: dict(info) for name, info in self._statements.items()}

    def list_materialized_tables(self) -> dict[str, dict]:
        return {name: dict(info) for name, info in self._mt_tables.items()}

    def get_statement_metrics(self, statement_name: str, compute_pool_id: str | None = None) -> dict:
        return dict(self._metrics)

    def get_materialized_table_metrics(self, mt_uid: str, compute_pool_id: str | None = None) -> dict:
        return dict(self._mt_metrics)

    def get_flink_pool_costs(self, start_date, end_date) -> dict[str, float]:
        return dict(self._pool_costs)

    def get_compute_pool_cfu(self, pool_id: str):
        return self._pool_cfu.get(pool_id)


class _RaisingClient:
    """Stand-in that raises on every call, simulating an unreachable backend."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def list_statement_phases(self) -> dict[str, str]:
        raise self._exc

    def list_statements(self) -> dict[str, dict]:
        raise self._exc

    def list_materialized_tables(self) -> dict[str, dict]:
        raise self._exc

    def get_statement_metrics(self, statement_name: str, compute_pool_id: str | None = None) -> dict:
        raise self._exc

    def get_materialized_table_metrics(self, mt_uid: str, compute_pool_id: str | None = None) -> dict:
        raise self._exc

    def get_flink_pool_costs(self, start_date, end_date) -> dict[str, float]:
        raise self._exc

    def get_compute_pool_cfu(self, pool_id: str):
        raise self._exc


def _fake_client(
    phases: dict[str, str] | None = None,
    metrics: dict | None = None,
    mt_tables: dict[str, dict] | None = None,
    mt_metrics: dict | None = None,
    statements: dict[str, dict] | None = None,
    pool_costs: dict[str, float] | None = None,
    pool_cfu: dict[str, float] | None = None,
) -> _FakeClient:
    return _FakeClient(
        phases=phases, metrics=metrics, mt_tables=mt_tables,
        mt_metrics=mt_metrics, statements=statements,
        pool_costs=pool_costs, pool_cfu=pool_cfu,
    )


def _raising_client(exc: Exception) -> _RaisingClient:
    return _RaisingClient(exc)


def test_live_status_maps_phases():
    # Key the fake Statements API by the nodes' real statement_name (read from
    # the descriptor) so this survives descriptor regeneration.
    graph = descriptor.get_graph("c360")
    sn = {n.id: n.statement_name for n in graph.nodes}
    client = _fake_client(phases={
        sn["src_customers"]: "RUNNING",
        sn["fct_c360_profile"]: "FAILED",
    })
    status = providers.LiveProvider(client=client).get_status(graph)
    byid = {s.node_id: s.phase for s in status.statements}
    assert byid["src_customers"] == "RUNNING" and byid["fct_c360_profile"] == "FAILED"


def test_live_unknown_phase_becomes_UNKNOWN():
    client = _fake_client(phases={})  # statement not reported
    status = providers.LiveProvider(client=client).get_status(descriptor.get_graph("c360"))
    assert all(s.phase in {"UNKNOWN"} or s.phase for s in status.statements)
    assert any(s.phase == "UNKNOWN" for s in status.statements)


def test_live_missing_metric_is_none():
    # fct_c360_profile is a materialized table, so metrics come from the MT path;
    # fields the MT API doesn't return (the rate counters) stay None.
    client = _fake_client(
        mt_tables={"fct_c360_profile": {"phase": "RUNNING", "uid": "mt-1"}},
        mt_metrics={"compute_pool_cfu": 3.0},  # no rate fields
    )
    m = providers.LiveProvider(client=client).get_metrics(descriptor.get_graph("c360"), "fct_c360_profile")
    assert m.compute_pool_cfu == 3.0 and m.messages_in_per_sec is None


def test_live_unreachable_does_not_raise():
    client = _raising_client(httpx.ConnectError("boom"))
    status = providers.LiveProvider(client=client).get_status(descriptor.get_graph("c360"))
    assert status.rollup.total == 11
    assert all(s.phase == "UNKNOWN" for s in status.statements)


def test_live_status_from_materialized_tables():
    # Materialized tables are keyed by table name (= graph node id/label), not
    # the dbt statement name — the MT API is their source of truth.
    client = _fake_client(mt_tables={
        "dim_transactions": {"phase": "RUNNING", "uid": "mt-1"},
        "fct_c360_profile": {"phase": "FAILED", "uid": "mt-2"},
    })
    status = providers.LiveProvider(client=client).get_status(descriptor.get_graph("c360"))
    byid = {s.node_id: s.phase for s in status.statements}
    assert byid["dim_transactions"] == "RUNNING" and byid["fct_c360_profile"] == "FAILED"


def test_live_mt_metrics_populate_cfu():
    client = _fake_client(
        mt_tables={"fct_c360_profile": {"phase": "RUNNING", "uid": "mt-1"}},
        mt_metrics={"compute_pool_cfu": 3.0},
    )
    m = providers.LiveProvider(client=client).get_metrics(descriptor.get_graph("c360"), "fct_c360_profile")
    assert m.phase == "RUNNING" and m.compute_pool_cfu == 3.0


def test_live_mt_node_sql_comes_from_materialized_table_spec():
    # A materialized table's defining SQL is read from the MT list (spec.query),
    # since its DDL statement isn't in the Statements list.
    client = _fake_client(
        mt_tables={"fct_c360_profile": {"phase": "RUNNING", "uid": "mt-1", "sql": "SELECT 1 FROM src"}},
    )
    m = providers.LiveProvider(client=client).get_metrics(descriptor.get_graph("c360"), "fct_c360_profile")
    assert m.sql == "SELECT 1 FROM src"


def _mixed_graph() -> Graph:
    """One materialized node and one streaming node, so metrics routing can be
    asserted per table_type (the c360 descriptor is all-materialized)."""
    return Graph(
        nodes=[
            GraphNode(id="mt_node", type="statement", label="mt_node",
                      statement_name="stmt-mt", topic="mt_node", table_type="materialized_table"),
            GraphNode(id="stream_node", type="statement", label="stream_node",
                      statement_name="stmt-stream", topic="stream_node", table_type="streaming_table"),
        ],
        edges=[],
    )


def test_live_materialized_node_metrics_use_mt_uid_not_statement():
    # A materialized table's metrics come only from the MT path (UID-scoped).
    # The statement path is never consulted, so its pending_records is ignored.
    client = _fake_client(
        metrics={"pending_records": 5},  # statement path — must be ignored
        mt_tables={"mt_node": {"phase": "RUNNING", "uid": "mt-1"}},
        mt_metrics={"compute_pool_cfu": 3.0},  # MT path — used
    )
    m = providers.LiveProvider(client=client).get_metrics(_mixed_graph(), "mt_node")
    assert m.compute_pool_cfu == 3.0
    assert m.pending_records is None


def test_live_streaming_node_metrics_use_statement_name_not_mt():
    # A streaming table's metrics come only from the statement path (name-scoped).
    # The MT path is never consulted, even though an MT entry happens to match.
    client = _fake_client(
        metrics={"pending_records": 7, "compute_pool_cfu": 2.0},  # statement path — used
        mt_tables={"stream_node": {"phase": "RUNNING", "uid": "mt-9"}},
        mt_metrics={"compute_pool_cfu": 99.0},  # MT path — must be ignored
    )
    m = providers.LiveProvider(client=client).get_metrics(_mixed_graph(), "stream_node")
    assert m.pending_records == 7
    assert m.compute_pool_cfu == 2.0  # statement path, not the MT's 99.0


def test_uptime_seconds_from_iso_created_at():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert providers._uptime_seconds("2026-01-01T11:00:00Z", now=now) == 3600


def test_uptime_seconds_none_when_missing_or_unparseable():
    assert providers._uptime_seconds(None) is None
    assert providers._uptime_seconds("not-a-timestamp") is None


def test_uptime_seconds_none_when_created_in_future():
    # Clock skew / a not-yet-started statement must not report negative uptime.
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert providers._uptime_seconds("2026-01-01T13:00:00Z", now=now) is None


def test_live_streaming_node_sql_comes_from_statement_object():
    # A streaming table is a regular Flink statement, so its defining SQL comes
    # from the statement object (spec.statement), matched by statement_name —
    # mirroring how the MT branch pulls SQL from the materialized-table spec.
    client = _fake_client(
        metrics={"pending_records": 7},
        statements={"stmt-stream": {"phase": "RUNNING", "uid": "s-1",
                                    "sql": "INSERT INTO stream_node SELECT * FROM src"}},
    )
    m = providers.LiveProvider(client=client).get_metrics(_mixed_graph(), "stream_node")
    assert m.sql == "INSERT INTO stream_node SELECT * FROM src"


def test_live_streaming_node_uptime_from_statement_created_at():
    # uptime_seconds for a streaming table is derived from the statement object's
    # metadata.created_at.
    client = _fake_client(
        statements={"stmt-stream": {"phase": "RUNNING", "uid": "s-1", "sql": "X",
                                    "created_at": "2020-01-01T00:00:00Z"}},
    )
    m = providers.LiveProvider(client=client).get_metrics(_mixed_graph(), "stream_node")
    assert m.uptime_seconds is not None and m.uptime_seconds > 0


def test_live_mt_node_uptime_from_created_at():
    # uptime_seconds for a materialized table is derived from the MT object's
    # metadata.created_at.
    client = _fake_client(
        mt_tables={"mt_node": {"phase": "RUNNING", "uid": "mt-1",
                               "created_at": "2020-01-01T00:00:00Z"}},
    )
    m = providers.LiveProvider(client=client).get_metrics(_mixed_graph(), "mt_node")
    assert m.uptime_seconds is not None and m.uptime_seconds > 0


# --- real-ConfluentClient HTTP-layer tests (httpx mocked, no network) ---
#
# The tests above inject a fake at the client boundary, so they never
# exercise the real URLs. These patch httpx itself to assert the real
# ConfluentClient hits the correct Confluent endpoints with HTTP Basic auth.


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D401 - mimic httpx.Response
        return None

    def json(self) -> dict:
        return self._payload


def _settings(**overrides) -> types.SimpleNamespace:
    base = dict(
        CONFLUENT_CLOUD_API_KEY="ck",
        CONFLUENT_CLOUD_API_SECRET="cs",
        FLINK_COMPUTE_POOL_ID="lfcp-x",
        FLINK_REST_ENDPOINT="https://flink.us-east-2.aws.confluent.cloud",
        FLINK_API_KEY="fk",
        FLINK_API_SECRET="fs",
        FLINK_ORG_ID="org-1",
        FLINK_ENV_ID="env-1",
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_statement_metrics_query_groups_by_statement_not_eq_filter(monkeypatch):
    # resource.flink_statement.name is NOT an authorized-resource filter — an EQ
    # filter on it returns empty. The statement per-node metrics must instead
    # filter by the authorized compute pool and GROUP BY the statement name, then
    # pick the target statement out of the grouped result.
    calls: list[dict] = []

    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002 - match httpx signature
        calls.append({"url": url, "auth": auth, "body": json})
        return _Resp({"data": []})

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    client.get_statement_metrics("dbt-streamhouse-fct-crm-by-country-5ab51e")

    # Four scoped queries: pending_records, pool CFUs, and the two record-count
    # counters (in/out) that back messages_in/out_per_sec.
    assert len(calls) == 4
    for call in calls:
        # Regression guard: telemetry host, not api.confluent.cloud; HTTP Basic (not bearer).
        assert call["url"] == "https://api.telemetry.confluent.cloud/v2/metrics/cloud/query"
        assert call["auth"] == ("ck", "cs")
        body = call["body"]
        # 422 regression guard: intervals is required and must be present/non-empty.
        assert body["intervals"] and "/" in body["intervals"][0]
        assert body["granularity"] == "PT1M"

    bodies_by_metric = {c["body"]["aggregations"][0]["metric"]: c["body"] for c in calls}
    assert "io.confluent.flink/pending_records" in bodies_by_metric
    assert "io.confluent.flink/compute_pool_utilization/current_cfus" in bodies_by_metric
    assert "io.confluent.flink/num_records_in" in bodies_by_metric
    assert "io.confluent.flink/num_records_out" in bodies_by_metric

    # The per-statement metrics (pending + the two counters) must GROUP BY the
    # statement name and filter ONLY by the authorized compute pool — never an
    # EQ filter on resource.flink_statement.name (that returns empty).
    for metric in (
        "io.confluent.flink/pending_records",
        "io.confluent.flink/num_records_in",
        "io.confluent.flink/num_records_out",
    ):
        body = bodies_by_metric[metric]
        assert body["format"] == "GROUPED"
        assert "resource.flink_statement.name" in body["group_by"]
        assert "resource.compute_pool.id" in body["group_by"]
        # The filter scopes to the authorized pool and must NOT constrain the
        # statement name (the whole point of the fix).
        filter_blob = repr(body["filter"])
        assert "resource.compute_pool.id" in filter_blob
        assert "lfcp-x" in filter_blob
        assert "resource.flink_statement.name" not in filter_blob


def test_statement_metrics_picks_target_statement_from_grouped_data(monkeypatch):
    # The grouped response carries every statement in the pool; the method must
    # return only the requested statement's values and ignore the rest.
    target = "dbt-streamhouse-fct-crm-by-country-5ab51e"
    other = "dbt-streamhouse-fct-crm-by-gender-72cff3"

    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002
        metric = json["aggregations"][0]["metric"]
        if metric == "io.confluent.flink/pending_records":
            return _Resp({"data": [
                {"resource.flink_statement.name": other, "points": [
                    {"timestamp": "2026-10-24T10:05:00Z", "value": 999}]},
                {"resource.flink_statement.name": target, "points": [
                    {"timestamp": "2026-10-24T10:00:00Z", "value": 10},
                    {"timestamp": "2026-10-24T10:05:00Z", "value": 4200}]},  # latest
            ]})
        if metric == "io.confluent.flink/num_records_in":
            return _Resp({"data": [
                {"resource.flink_statement.name": target, "points": [
                    {"timestamp": "2026-10-24T10:05:00Z", "value": 120}]},
            ]})
        if metric == "io.confluent.flink/num_records_out":
            return _Resp({"data": [
                {"resource.flink_statement.name": target, "points": [
                    {"timestamp": "2026-10-24T10:05:00Z", "value": 60}]},
            ]})
        # pool CFU — pool-scoped, flat points.
        return _Resp({"data": [{"timestamp": "2026-10-24T10:05:00Z", "value": 2.0}]})

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    metrics = client.get_statement_metrics(target)

    # Latest point for the TARGET statement only (not the other statement's 999).
    assert metrics["pending_records"] == 4200
    assert metrics["compute_pool_cfu"] == 2.0
    # COUNTER value is records per PT1M interval -> per-second rate divides by 60.
    assert metrics["messages_in_per_sec"] == 120 / 60
    assert metrics["messages_out_per_sec"] == 60 / 60


def test_statement_metrics_absent_statement_yields_no_rate(monkeypatch):
    # If the requested statement isn't present in the grouped data, its metrics
    # are simply absent (None downstream) — never another statement's values.
    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002
        return _Resp({"data": [
            {"resource.flink_statement.name": "someone-else", "points": [
                {"timestamp": "2026-10-24T10:05:00Z", "value": 500}]},
        ]})

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    metrics = client.get_statement_metrics("dbt-streamhouse-fct-crm-by-country-5ab51e")

    assert "pending_records" not in metrics
    assert "messages_in_per_sec" not in metrics


def test_list_materialized_tables_parses_name_phase_uid(monkeypatch):
    captured: dict = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["auth"] = auth
        return _Resp({"data": [
            {"name": "src_customers", "metadata": {"uid": "mt-1", "created_at": "2026-01-01T00:00:00Z"},
             "status": {"phase": "RUNNING", "version": 3},
             "spec": {"query": "SELECT * FROM cust"}},
            {"name": "fct_c360_profile", "metadata": {"uid": "mt-2"},
             "status": {"phase": "FAILED", "version": 1}},  # no spec.query, no created_at
        ]})

    monkeypatch.setattr(confluent_client.httpx, "get", fake_get)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    tables = client.list_materialized_tables()

    assert captured["url"] == (
        "https://flink.us-east-2.aws.confluent.cloud/sql/v1/organizations/"
        "org-1/environments/env-1/materialized-tables"
    )
    assert captured["auth"] == ("fk", "fs")
    # The MT's defining SQL (spec.query) and start time (metadata.created_at) ride
    # along for the drill-down panel; each is None when the spec/metadata omits it.
    assert tables == {
        "src_customers": {"phase": "RUNNING", "uid": "mt-1", "version": 3,
                          "sql": "SELECT * FROM cust", "created_at": "2026-01-01T00:00:00Z"},
        "fct_c360_profile": {"phase": "FAILED", "uid": "mt-2", "version": 1,
                             "sql": None, "created_at": None},
    }


def test_mt_metrics_query_scopes_by_pool_and_uid(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002
        calls.append({"url": url, "auth": auth, "body": json})
        return _Resp({"data": [{"timestamp": "2026-10-26T10:05:00Z", "value": 1.5}]})

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    metrics = client.get_materialized_table_metrics("mt-uid-123")

    bodies_by_metric = {c["body"]["aggregations"][0]["metric"]: c["body"] for c in calls}
    cfu_metric = "io.confluent.flink/materialized_table_utilization/current_cfus"
    assert cfu_metric in bodies_by_metric
    body = bodies_by_metric[cfu_metric]
    assert calls[0]["url"] == "https://api.telemetry.confluent.cloud/v2/metrics/cloud/query"
    # The principal is authorized on the compute pool, so every MT query must
    # filter by BOTH the authorized pool id AND the MT uid — a uid-only filter
    # 403s ("Query must filter by at least one of your authorized resources").
    scoped = {f["field"]: f["value"] for f in body["filter"]["filters"]}
    assert body["filter"]["op"] == "AND"
    assert scoped["resource.compute_pool.id"] == "lfcp-x"
    assert scoped[confluent_client._MT_UID_DIMENSION] == "mt-uid-123"
    assert body["intervals"] and "/" in body["intervals"][0]
    assert metrics["compute_pool_cfu"] == 1.5


def test_mt_metrics_includes_record_rates(monkeypatch):
    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002
        metric = json["aggregations"][0]["metric"]
        # Every MT record query must be AND-scoped by the authorized pool + uid.
        fields = {f["field"]: f["value"] for f in json["filter"]["filters"]}
        assert fields["resource.compute_pool.id"] == "lfcp-x"
        assert fields[confluent_client._MT_UID_DIMENSION] == "mt-9"
        value = {"io.confluent.flink/num_records_in": 300,
                 "io.confluent.flink/num_records_out": 180}.get(metric, 0.25)
        return _Resp({"data": [{"timestamp": "2026-10-26T10:05:00Z", "value": value}]})

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    metrics = client.get_materialized_table_metrics("mt-9")

    assert metrics["compute_pool_cfu"] == 0.25
    assert metrics["messages_in_per_sec"] == 300 / 60
    assert metrics["messages_out_per_sec"] == 180 / 60


def test_mt_metrics_without_pool_skips_query(monkeypatch):
    # Without a compute pool to scope to, the MT query would 403 — skip it.
    calls: list[dict] = []
    monkeypatch.setattr(confluent_client.httpx, "post", lambda *a, **k: calls.append(1))
    client = confluent_client.ConfluentClient(settings_obj=_settings(FLINK_COMPUTE_POOL_ID=None))
    assert client.get_materialized_table_metrics("mt-uid-123") == {}
    assert calls == []


def test_mt_metrics_empty_uid_skips_query(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(confluent_client.httpx, "post", lambda *a, **k: calls.append(1))
    client = confluent_client.ConfluentClient(settings_obj=_settings())
    assert client.get_materialized_table_metrics("") == {}
    assert calls == []  # no HTTP call when the uid is unknown


def test_metrics_forbidden_is_swallowed(monkeypatch):
    # A 403 (missing MetricsViewer role) must degrade to empty metrics, never raise.
    req = httpx.Request("POST", confluent_client._METRICS_API_BASE_URL)
    resp = httpx.Response(403, request=req)

    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002
        raise httpx.HTTPStatusError("forbidden", request=req, response=resp)

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    metrics = client.get_statement_metrics("models-c360-sources-pipeline-src-customers")

    assert metrics == {}


def test_list_statements_parses_name_phase_sql_uid(monkeypatch):
    captured: dict = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["auth"] = auth
        return _Resp({"data": [
            {"name": "stmt-a", "metadata": {"uid": "s-1", "created_at": "2026-01-01T00:00:00Z"},
             "status": {"phase": "RUNNING"},
             "spec": {"statement": "INSERT INTO a SELECT * FROM b"}},
            {"name": "stmt-b", "metadata": {"uid": "s-2"},
             "status": {"phase": "FAILED"}},  # no spec.statement, no created_at
        ]})

    monkeypatch.setattr(confluent_client.httpx, "get", fake_get)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    statements = client.list_statements()

    assert captured["url"] == (
        "https://flink.us-east-2.aws.confluent.cloud/sql/v1/organizations/"
        "org-1/environments/env-1/statements"
    )
    assert captured["auth"] == ("fk", "fs")
    # The statement's defining SQL (spec.statement) and start time
    # (metadata.created_at) ride along for the drill-down panel; each is None when
    # the statement omits it.
    assert statements == {
        "stmt-a": {"phase": "RUNNING", "uid": "s-1",
                   "sql": "INSERT INTO a SELECT * FROM b", "created_at": "2026-01-01T00:00:00Z"},
        "stmt-b": {"phase": "FAILED", "uid": "s-2", "sql": None, "created_at": None},
    }


def test_statement_phases_uses_flink_endpoint_with_basic_auth(monkeypatch):
    captured: dict = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["auth"] = auth
        return _Resp({"data": []})

    monkeypatch.setattr(confluent_client.httpx, "get", fake_get)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    client.list_statement_phases()

    assert captured["url"] == (
        "https://flink.us-east-2.aws.confluent.cloud/sql/v1/organizations/"
        "org-1/environments/env-1/statements"
    )
    assert captured["auth"] == ("fk", "fs")


# ---------------------------------------------------------------------------
# Cost API client (Task 5): get_flink_pool_costs / get_compute_pool_cfu
# ---------------------------------------------------------------------------


def test_get_flink_pool_costs_sums_by_pool(monkeypatch):
    def fake_get(url, params=None, auth=None, timeout=None):
        return _Resp({
            "data": [
                {"product": "FLINK", "resource": {"id": "lfcp-a"}, "amount": 1.5},
                {"product": "FLINK", "resource": {"id": "lfcp-a"}, "amount": 2.0},
                {"product": "FLINK", "resource": {"id": "lfcp-b"}, "amount": 4.0},
                {"product": "KAFKA", "resource": {"id": "lkc-x"}, "amount": 99.0},
            ],
            "metadata": {},
        })

    monkeypatch.setattr(confluent_client.httpx, "get", fake_get)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    totals = client.get_flink_pool_costs(date(2026, 10, 1), date(2026, 10, 30))

    # Non-FLINK line items excluded; FLINK items summed per compute pool.
    assert totals == {"lfcp-a": 3.5, "lfcp-b": 4.0}


def test_get_flink_pool_costs_follows_pagination(monkeypatch):
    calls: list[dict] = []

    def fake_get(url, params=None, auth=None, timeout=None):
        calls.append({"url": url, "params": params})
        if len(calls) == 1:
            return _Resp({
                "data": [{"product": "FLINK", "resource": {"id": "lfcp-a"}, "amount": 1.0}],
                "metadata": {"next": "https://api.confluent.cloud/billing/v1/costs?page_token=TOK"},
            })
        return _Resp({
            "data": [{"product": "FLINK", "resource": {"id": "lfcp-a"}, "amount": 2.0}],
            "metadata": {},
        })

    monkeypatch.setattr(confluent_client.httpx, "get", fake_get)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    totals = client.get_flink_pool_costs(date(2026, 10, 1), date(2026, 10, 30))

    assert totals == {"lfcp-a": 3.0}  # both pages summed
    assert len(calls) == 2
    assert "page_token=TOK" in calls[1]["url"]  # second request followed the next token


def test_get_flink_pool_costs_best_effort(monkeypatch):
    def boom(*a, **k):
        raise httpx.HTTPError("down")

    monkeypatch.setattr(confluent_client.httpx, "get", boom)
    client = confluent_client.ConfluentClient(settings_obj=_settings())
    assert client.get_flink_pool_costs(date(2026, 10, 1), date(2026, 10, 30)) == {}

    # Missing credentials short-circuits with no HTTP call.
    calls: list[int] = []
    monkeypatch.setattr(confluent_client.httpx, "get", lambda *a, **k: calls.append(1))
    client2 = confluent_client.ConfluentClient(settings_obj=_settings(CONFLUENT_CLOUD_API_KEY=None))
    assert client2.get_flink_pool_costs(date(2026, 10, 1), date(2026, 10, 30)) == {}
    assert calls == []


def test_get_compute_pool_cfu_returns_latest(monkeypatch):
    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002
        return _Resp({"data": [
            {"timestamp": "2026-10-30T00:00:00Z", "value": 5.0},
            {"timestamp": "2026-10-30T00:01:00Z", "value": 7.0},
        ]})

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())
    assert client.get_compute_pool_cfu("lfcp-a") == 7.0

    def boom(*a, **k):
        raise httpx.HTTPError("x")

    monkeypatch.setattr(confluent_client.httpx, "post", boom)
    assert client.get_compute_pool_cfu("lfcp-a") is None


# ---------------------------------------------------------------------------
# LiveProvider.get_cost (Task 6)
# ---------------------------------------------------------------------------


def _crm_like_graph() -> Graph:
    """An owned crm statement (lfcp-crm) plus an imported/external c360 upstream
    (lfcp-c360), so cost attribution can be asserted to exclude the external pool."""
    return Graph(
        nodes=[
            GraphNode(id="owned", type="statement", label="owned",
                      statement_name="s1", topic="owned", is_product=True,
                      compute_pool_id="lfcp-crm", table_type="streaming_table"),
            GraphNode(id="imported", type="statement", label="imported",
                      statement_name="s2", topic="imported", external=True,
                      compute_pool_id="lfcp-c360", table_type="materialized_table"),
        ],
        edges=[],
    )


def test_live_get_cost_sums_owned_pools_only():
    client = _fake_client(pool_costs={"lfcp-crm": 10.0, "lfcp-c360": 5.0}, pool_cfu={"lfcp-crm": 3.0})
    cost = providers.LiveProvider(client=client).get_cost(_crm_like_graph())
    assert cost.amount == 10.0  # external lfcp-c360 excluded
    assert cost.pool_ids == ["lfcp-crm"]
    assert cost.available is True
    assert cost.cfu == 3.0


def test_live_get_cost_unavailable_when_no_matching_costs():
    client = _fake_client(pool_costs={})  # 403 / data lag -> nothing for our pool
    cost = providers.LiveProvider(client=client).get_cost(_crm_like_graph())
    assert cost.available is False
    assert cost.amount == 0.0


def test_live_get_cost_partial_month_available():
    client = _fake_client(pool_costs={"lfcp-crm": 1.0})
    cost = providers.LiveProvider(client=client).get_cost(_crm_like_graph())
    assert cost.available is True
    assert cost.amount == 1.0


def test_live_get_cost_best_effort_on_raise():
    client = _raising_client(httpx.ConnectError("boom"))
    cost = providers.LiveProvider(client=client).get_cost(_crm_like_graph())
    assert cost.available is False  # client failure degrades, never raises


def test_live_get_cost_no_owned_pools_is_unavailable():
    graph = Graph(nodes=[GraphNode(id="imported", type="statement", label="imported",
                                   statement_name="s", external=True, compute_pool_id="lfcp-c360")],
                  edges=[])
    cost = providers.LiveProvider(client=_fake_client(pool_costs={"lfcp-c360": 9.0})).get_cost(graph)
    assert cost.available is False and cost.pool_ids == []


# ---------------------------------------------------------------------------
# Pool-aware metrics (Task 8): node's compute_pool_id scopes the Metrics query
# ---------------------------------------------------------------------------


def _pool_filter_values(body: dict) -> list[str]:
    """Collect every resource.compute_pool.id value in a Metrics API filter."""
    out: list[str] = []

    def walk(f: dict) -> None:
        if not isinstance(f, dict):
            return
        if f.get("field") == "resource.compute_pool.id":
            out.append(f.get("value"))
        for sub in f.get("filters", []) or []:
            walk(sub)

    walk(body.get("filter", {}))
    return out


def test_statement_metrics_uses_node_compute_pool(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002
        calls.append(json)
        return _Resp({"data": []})

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())  # default pool lfcp-x

    client.get_statement_metrics("some-statement", compute_pool_id="lfcp-crm")

    assert calls, "expected Metrics API queries"
    for body in calls:
        assert _pool_filter_values(body) == ["lfcp-crm"]  # node pool, not the default lfcp-x


def test_statement_metrics_defaults_to_settings_pool(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, json=None, auth=None, timeout=None):  # noqa: A002
        calls.append(json)
        return _Resp({"data": []})

    monkeypatch.setattr(confluent_client.httpx, "post", fake_post)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    client.get_statement_metrics("some-statement")  # no override -> default pool

    for body in calls:
        assert _pool_filter_values(body) == ["lfcp-x"]


def test_live_get_cost_zero_amount_is_unavailable():
    # A matched pool whose cost sums to (effectively) zero must NOT show a $0
    # banner: available is False once the rounded amount is 0.
    client = _fake_client(pool_costs={"lfcp-crm": 0.0})
    cost = providers.LiveProvider(client=client).get_cost(_crm_like_graph())
    assert cost.available is False
    assert cost.amount == 0.0


# ---------------------------------------------------------------------------
# Flink REST list pagination (bug: crm streaming statements fell off page 1)
# ---------------------------------------------------------------------------


def test_list_statement_phases_follows_pagination(monkeypatch):
    calls: list[str] = []

    def fake_get(url, params=None, auth=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            return _Resp({
                "data": [{"name": "s1", "status": {"phase": "RUNNING"}}],
                "metadata": {"next": "https://flink.test/sql/v1/.../statements?page_token=T2"},
            })
        return _Resp({"data": [{"name": "s2", "status": {"phase": "RUNNING"}}], "metadata": {}})

    monkeypatch.setattr(confluent_client.httpx, "get", fake_get)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    phases = client.list_statement_phases()

    assert phases == {"s1": "RUNNING", "s2": "RUNNING"}  # both pages merged
    assert len(calls) == 2
    assert "page_token=T2" in calls[1]


def test_list_materialized_tables_follows_pagination(monkeypatch):
    calls: list[str] = []

    def fake_get(url, params=None, auth=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            return _Resp({
                "data": [{"name": "mt1", "status": {"phase": "RUNNING"}, "metadata": {"uid": "u1"}}],
                "metadata": {"next": "https://flink.test/sql/v1/.../materialized-tables?page_token=T2"},
            })
        return _Resp({
            "data": [{"name": "mt2", "status": {"phase": "RUNNING"}, "metadata": {"uid": "u2"}}],
            "metadata": {},
        })

    monkeypatch.setattr(confluent_client.httpx, "get", fake_get)
    client = confluent_client.ConfluentClient(settings_obj=_settings())

    tables = client.list_materialized_tables()

    assert set(tables) == {"mt1", "mt2"}  # both pages merged
    assert len(calls) == 2
