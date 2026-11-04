"""Orchestration layer for CEP scenario execution.

Builds the scripted transaction sequence and writes it to Postgres; the
Debezium CDC connector publishes the rows to Kafka.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from scenarios import registry, runner
from scenarios.models import ScenarioResult
from transactions import db_sink
from transactions.models import Transaction

__all__ = ["UnknownScenarioError"]


class UnknownScenarioError(ValueError):
    """Raised when the requested scenario_id is not in the registry."""


def run(scenario_id: str) -> ScenarioResult:
    """Inject a scripted transaction sequence and return the result.

    Raises:
        UnknownScenarioError: scenario_id not found in the registry.
    """
    defn = registry.SCENARIOS.get(scenario_id)
    if defn is None:
        raise UnknownScenarioError(scenario_id)

    triggered_at = datetime.now(tz=timezone.utc)
    creates = runner.build_transactions(defn, now=triggered_at)

    # Materialise to Transaction objects with generated IDs (same as db_sink.create)
    now_utc = datetime.now(tz=timezone.utc)
    txns = [
        Transaction(transaction_id=uuid4(), created_at=now_utc, **c.model_dump())
        for c in creates
    ]

    db_sink.create_many(txns)

    return ScenarioResult(
        scenario_id=defn.scenario_id,
        pattern=defn.pattern,
        label=defn.label,
        triggered_at=triggered_at,
        transactions=txns,
    )


def list_scenarios() -> list:
    """Return all registered scenario definitions."""
    return list(registry.SCENARIOS.values())
