"""Run a bounded Flink SQL *snapshot query* via the ``confluent-sql`` driver.

``confluent-sql`` is a DB-API v2 driver for Confluent Cloud for Apache Flink;
its default cursor runs in **snapshot mode** — a point-in-time read that returns
the table's current state (one row per primary key) as a finite result set and
terminates. That is exactly what the analytics snapshot reads need (the CRM
data products and the by-id profile lookup), so no changelog collapsing is
required here.

Like the other analytics clients, this is **best-effort**: incomplete
credentials or any error (connect, execute, fetch) resolve to ``[]`` so the
dashboard shows an empty state — it never raises.
"""

from __future__ import annotations

import logging

import confluent_sql

import config

logger = logging.getLogger(__name__)

# Settings `confluent_sql.connect()` needs. Snapshot queries run on the dedicated
# snapshot-q-pool (FLINK_SNAPSHOT_COMPUTE_POOL_ID, Terraform `sn_pool`) — never
# on the pipeline pools, and with no fallback to them. The environment resolves
# the Flink catalog, so no FLINK_CATALOG; the cluster display name (FLINK_DATABASE) plus
# its id (KAFKA_CLUSTER_ID) resolve the database without a CMK lookup.
_CONFIG_FIELDS = (
    "FLINK_ORG_ID",
    "FLINK_ENV_ID",
    "CLOUD_PROVIDER",
    "CLOUD_REGION",
    "FLINK_SNAPSHOT_COMPUTE_POOL_ID",
    "FLINK_API_KEY",
    "FLINK_API_SECRET",
    "FLINK_DATABASE",
    "KAFKA_CLUSTER_ID",
)


class ConfluentSqlClient:
    """Thin, failure-tolerant client for one Flink SQL snapshot query."""

    def __init__(self, settings_obj: config.Settings | None = None) -> None:
        self._settings = settings_obj if settings_obj is not None else config.settings

    def _missing_settings(self) -> list[str]:
        """Names of the required settings that are unset/empty."""
        return [f for f in _CONFIG_FIELDS if not getattr(self._settings, f, None)]

    def query(self, sql: str) -> list[dict]:
        """Run one snapshot ``SELECT``; return ``[{column: value}]``.

        Returns ``[]`` when credentials are incomplete or on any failure.
        """
        missing = self._missing_settings()
        if missing:
            logger.warning(
                "ConfluentSqlClient: skipping snapshot query — these settings are "
                "unset: %s. (Live analytics needs all "
                "FLINK_*/CLOUD_* settings incl. KAFKA_CLUSTER_ID.)",
                ", ".join(missing),
            )
            return []

        s = self._settings
        try:
            conn = confluent_sql.connect(
                organization_id=s.FLINK_ORG_ID,
                environment_id=s.FLINK_ENV_ID,
                cloud_provider=s.CLOUD_PROVIDER,
                cloud_region=s.CLOUD_REGION,
                compute_pool_id=s.FLINK_SNAPSHOT_COMPUTE_POOL_ID,
                flink_api_key=s.FLINK_API_KEY,
                flink_api_secret=s.FLINK_API_SECRET,
                database=s.FLINK_DATABASE,
                database_kafka_cluster_id=s.KAFKA_CLUSTER_ID,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort: any connect failure → []
            logger.warning("ConfluentSqlClient: connect failed: %s", exc, exc_info=True)
            return []

        try:
            cur = conn.cursor()  # snapshot mode is the default
            try:
                cur.execute(sql)
                columns = [d[0] for d in (cur.description or [])]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
            finally:
                cur.close()
        except Exception as exc:  # noqa: BLE001 — best-effort: any query failure → []
            logger.warning("ConfluentSqlClient: snapshot query failed: %s: %s", sql, exc, exc_info=True)
            return []
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — a failed close must not mask the result
                logger.warning("ConfluentSqlClient: failed to close connection", exc_info=True)
