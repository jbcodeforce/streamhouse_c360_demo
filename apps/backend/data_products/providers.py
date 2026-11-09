"""Status/metrics providers for the Data Products graph page.

``LiveProvider`` talks to Confluent Cloud + Flink. ``get_provider()`` returns
a ``LiveProvider``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Protocol

from data_products.confluent_client import ConfluentClient, ConfluentClientProtocol
from data_products.models import (
    CostResponse,
    Graph,
    NodeMetrics,
    NodeStatus,
    StatusResponse,
    StatusRollup,
)

logger = logging.getLogger(__name__)

_VALID_PHASES = frozenset({"RUNNING", "PENDING", "DEGRADED", "FAILED", "STOPPED", "UNKNOWN"})


def _uptime_seconds(created_at: str | None, now: datetime | None = None) -> int | None:
    """Whole seconds a node has been running, from its ``metadata.created_at``.

    Returns ``None`` when ``created_at`` is absent/unparseable, or when it is in
    the future (clock skew / a not-yet-started node) — never a negative uptime.
    ``now`` defaults to the current UTC time (injected in tests for determinism).
    """
    if not created_at:
        return None
    try:
        # Accept a trailing "Z" (UTC) as well as explicit offsets.
        started = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    delta = (current - started).total_seconds()
    return int(delta) if delta >= 0 else None


def _owned_pool_ids(graph: Graph) -> list[str]:
    """Sorted, distinct compute pool ids used by this product's OWN statements.

    External (cross-product upstream) nodes are excluded so a product's cost
    counts only the pools it owns — their pool belongs to the owning product.
    """
    return sorted(
        {
            node.compute_pool_id
            for node in graph.nodes
            if node.type == "statement" and not node.external and node.compute_pool_id
        }
    )


def _month_to_date(now: datetime | None = None) -> tuple[date, date]:
    """``(first_of_month, today)`` in UTC — the Cost API window for "this month"."""
    today = (now or datetime.now(timezone.utc)).date()
    return today.replace(day=1), today


class StatusProvider(Protocol):
    def get_status(self, graph: Graph) -> StatusResponse: ...

    def get_metrics(self, graph: Graph, node_id: str) -> NodeMetrics: ...

    def get_cost(self, graph: Graph) -> CostResponse: ...


class LiveProvider:
    """Best-effort Confluent Cloud + Flink status/metrics provider.

    Talks to Confluent Cloud + Flink via an injected ``ConfluentClient``
    (defaults to a real one built from ``config.settings``). Live mode is
    explicitly best-effort and failure-tolerant: any error raised by the
    client — network failure, bad credentials, malformed response, or
    anything else — is caught here so it never propagates out of
    ``get_status``/``get_metrics``. On total failure every statement's phase
    becomes "UNKNOWN" and the response/metrics are still well-formed, so the
    graph page degrades gracefully instead of breaking.
    """

    def __init__(self, client: ConfluentClientProtocol | None = None) -> None:
        self._client: ConfluentClientProtocol = client if client is not None else ConfluentClient()

    def _safe_statement_phases(self) -> dict[str, str]:
        try:
            return self._client.list_statement_phases()
        except Exception:  # noqa: BLE001 — best-effort: never let this surface
            logger.warning("LiveProvider: list_statement_phases failed; reporting UNKNOWN", exc_info=True)
            return {}

    def _safe_materialized_tables(self) -> dict[str, dict]:
        """``{name: {"phase", "uid", "version"}}`` — the source of truth for the
        c360 nodes, which are materialized tables (not in the Statements list)."""
        try:
            return self._client.list_materialized_tables()
        except Exception:  # noqa: BLE001 — best-effort: never let this surface
            logger.warning("LiveProvider: list_materialized_tables failed; reporting UNKNOWN", exc_info=True)
            return {}

    @staticmethod
    def _merged_phases(statement_phases: dict[str, str], mt_tables: dict[str, dict]) -> dict[str, str]:
        """One phase lookup keyed by both statement names and MT table names.
        The two key spaces are distinct, so a node can resolve its phase by
        whichever identifier the backend keyed it under."""
        phases = dict(statement_phases)
        for name, info in mt_tables.items():
            if info.get("phase"):
                phases[name] = info["phase"]
        return phases

    @staticmethod
    def _normalize_phase(phase: str | None) -> str:
        return phase if phase in _VALID_PHASES else "UNKNOWN"

    @classmethod
    def _phase_for(cls, node, phases: dict[str, str]) -> str:
        for key in (node.id, node.label, node.statement_name):
            if key and key in phases:
                return cls._normalize_phase(phases[key])
        return "UNKNOWN"

    @staticmethod
    def _mt_entry_for(node, mt_tables: dict[str, dict]) -> dict | None:
        """The materialized-tables entry for this node, matched by table name =
        node id/label. Carries the UID (Metrics API resource id) and the
        defining SQL (spec.query)."""
        for key in (node.id, node.label):
            info = mt_tables.get(key)
            if info:
                return info
        return None

    def _safe_mt_metrics(self, uid: str, compute_pool_id: str | None = None) -> dict:
        try:
            return self._client.get_materialized_table_metrics(uid, compute_pool_id)
        except Exception:  # noqa: BLE001 — best-effort: never let this surface
            logger.warning("LiveProvider: get_materialized_table_metrics failed for uid=%s", uid, exc_info=True)
            return {}

    def _safe_statement_metrics(self, statement_name: str, compute_pool_id: str | None = None) -> dict:
        try:
            return self._client.get_statement_metrics(statement_name, compute_pool_id)
        except Exception:  # noqa: BLE001 — best-effort: never let this surface
            logger.warning("LiveProvider: get_statement_metrics failed for %s", statement_name, exc_info=True)
            return {}

    def _safe_statements(self) -> dict[str, dict]:
        """``{name: {"phase", "uid", "sql"}}`` — the statement objects, source of
        the defining SQL for streaming-table nodes (spec.statement)."""
        try:
            return self._client.list_statements()
        except Exception:  # noqa: BLE001 — best-effort: never let this surface
            logger.warning("LiveProvider: list_statements failed", exc_info=True)
            return {}

    def get_status(self, graph: Graph) -> StatusResponse:
        phases = self._merged_phases(self._safe_statement_phases(), self._safe_materialized_tables())
        statements = []
        for node in graph.nodes:
            if node.type != "statement":
                continue
            # Status is phase-only in live mode: a per-node backlog signal would
            # need a metric call per node per poll (N+1), and materialized tables
            # don't expose pending_records anyway. A DEGRADED/FAILED phase still
            # colors the node via the phase mapping.
            statements.append(
                NodeStatus(
                    node_id=node.id,
                    statement_name=node.statement_name,
                    phase=self._phase_for(node, phases),
                    lagging=False,
                )
            )
        rollup = StatusRollup(
            running=sum(1 for s in statements if s.phase == "RUNNING"),
            total=len(statements),
            lagging=sum(1 for s in statements if s.lagging),
        )
        return StatusResponse(statements=statements, rollup=rollup)

    def get_metrics(self, graph: Graph, node_id: str) -> NodeMetrics:
        node = next((n for n in graph.nodes if n.id == node_id), None)
        if node is None or node.type != "statement":
            return NodeMetrics(node_id=node_id, phase="UNKNOWN")

        statement_phases = self._safe_statement_phases()
        mt_tables = self._safe_materialized_tables()
        phases = self._merged_phases(statement_phases, mt_tables)

        # Metrics are scoped differently per table_type (mirrors the dbt
        # `materialized` config): a streaming_table is a regular statement,
        # scoped by statement name; a materialized_table is a hidden statement,
        # scoped by its MT UID (found via the materialized-tables REST API).
        # Query only the matching path — the other one's identifier doesn't
        # resolve for this kind of table. table_type is None for legacy/unset
        # nodes; treat that as materialized_table, the historical default for
        # the all-MT c360 pipeline.
        raw: dict = {}
        if node.table_type == "streaming_table":
            if node.statement_name:
                raw.update(self._safe_statement_metrics(node.statement_name, node.compute_pool_id))
                # A streaming table is a regular statement; its defining SQL lives
                # on the statement object (spec.statement), matched by name —
                # parallel to the MT branch reading spec.query below.
                entry = self._safe_statements().get(node.statement_name)
                if entry:
                    if entry.get("sql"):
                        raw["sql"] = entry["sql"]
                    uptime = _uptime_seconds(entry.get("created_at"))
                    if uptime is not None:
                        raw["uptime_seconds"] = uptime
        else:
            entry = self._mt_entry_for(node, mt_tables)
            if entry:
                if entry.get("uid"):
                    raw.update(self._safe_mt_metrics(entry["uid"], node.compute_pool_id))
                if entry.get("sql"):
                    raw["sql"] = entry["sql"]
                uptime = _uptime_seconds(entry.get("created_at"))
                if uptime is not None:
                    raw["uptime_seconds"] = uptime

        return NodeMetrics(
            node_id=node_id,
            phase=self._phase_for(node, phases),
            uptime_seconds=raw.get("uptime_seconds"),
            messages_in_per_sec=raw.get("messages_in_per_sec"),
            messages_out_per_sec=raw.get("messages_out_per_sec"),
            pending_records=raw.get("pending_records"),
            compute_pool_cfu=raw.get("compute_pool_cfu"),
            sql=raw.get("sql"),
        )

    def _safe_pool_costs(self, start: date, end: date) -> dict[str, float]:
        try:
            return self._client.get_flink_pool_costs(start, end)
        except Exception:  # noqa: BLE001 — best-effort: never let this surface
            logger.warning("LiveProvider: get_flink_pool_costs failed; cost unavailable", exc_info=True)
            return {}

    def _safe_pool_cfu(self, pool_id: str) -> float | None:
        try:
            return self._client.get_compute_pool_cfu(pool_id)
        except Exception:  # noqa: BLE001 — best-effort: never let this surface
            logger.warning("LiveProvider: get_compute_pool_cfu failed for pool=%s", pool_id, exc_info=True)
            return None

    def get_cost(self, graph: Graph) -> CostResponse:
        """Month-to-date Flink cost for this product's pipeline.

        Sums the Cost API's billed amount for the distinct pools the product's own
        (non-external) statements use. ``available`` is False when the product
        owns no pool or the Cost API returned nothing for its pools (lag, missing
        billing access, or failure) so the banner hides rather than showing $0.
        """
        pool_ids = _owned_pool_ids(graph)
        start, end = _month_to_date()
        if not pool_ids:
            return CostResponse(available=False, period_start=start, period_end=end)

        costs = self._safe_pool_costs(start, end)
        # Round before the availability check so floating-point noise on an
        # effectively-zero pool can't flip available to True and surface a "$0"
        # banner — available means "there is a positive cost to show".
        amount = round(sum(costs[p] for p in pool_ids if p in costs), 2)
        available = amount > 0

        cfu_values = [c for c in (self._safe_pool_cfu(p) for p in pool_ids) if c is not None]
        cfu = sum(cfu_values) if cfu_values else None

        return CostResponse(
            available=available,
            amount=amount,
            cfu=cfu,
            period_start=start,
            period_end=end,
            pool_ids=pool_ids,
        )


def get_provider() -> StatusProvider:
    """Return the status/metrics provider (always ``LiveProvider``)."""
    return LiveProvider()
