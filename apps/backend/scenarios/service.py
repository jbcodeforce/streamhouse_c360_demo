"""Orchestration layer for CEP scenario execution.

Builds the scripted transaction sequence, writes it to Postgres, and optionally
publishes the events to Kafka — using the same paths as transactions/service.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from config import settings
from scenarios import registry, runner
from scenarios.models import ScenarioResult
from transactions import db_sink, kafka_producer
from transactions.models import Transaction

logger = logging.getLogger("c360.scenarios.service")

_BATCH_FLUSH_TIMEOUT = 30.0

__all__ = ["UnknownScenarioError", "UnsupportedSinkError"]


class UnknownScenarioError(ValueError):
    """Raised when the requested scenario_id is not in the registry."""


class UnsupportedSinkError(Exception):
    """Raised when the sink is not postgres (scenarios require DB persistence)."""


def run(scenario_id: str) -> ScenarioResult:
    """Inject a scripted transaction sequence and return the result.

    Raises:
        UnknownScenarioError: scenario_id not found in the registry.
        UnsupportedSinkError: SINK is not "postgres".
    """
    defn = registry.SCENARIOS.get(scenario_id)
    if defn is None:
        raise UnknownScenarioError(scenario_id)
    if settings.SINK != "postgres":
        raise UnsupportedSinkError(settings.SINK)

    triggered_at = datetime.now(tz=timezone.utc)
    creates = runner.build_transactions(defn, now=triggered_at)

    # Materialise to Transaction objects with generated IDs (same as db_sink.create)
    now_utc = datetime.now(tz=timezone.utc)
    txns = [
        Transaction(transaction_id=uuid4(), created_at=now_utc, **c.model_dump())
        for c in creates
    ]

    db_sink.create_many(txns)

    if not settings.CDC_CONNECTOR_ENABLED and settings.KAFKA_PRODUCE_ENABLED:
        try:
            kafka_producer.produce_create_many(txns, flush_timeout=_BATCH_FLUSH_TIMEOUT)
        except Exception:
            logger.warning(
                "Kafka batch emit failed for scenario %s (%d events)",
                scenario_id, len(txns), exc_info=True,
            )

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
