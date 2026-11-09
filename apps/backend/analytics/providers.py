"""Snapshot providers for the C360 analytics dashboard.

All live reads go through the ``confluent-sql`` DB-API driver
(:class:`ConfluentSqlClient`), whose default cursor runs in **snapshot mode** —
a point-in-time read returning current state (one row per primary key) as a
finite result set.

Two live shapes live here:

* the dashboard aggregates — five ``fct_crm_*`` pre-aggregated products read
  concurrently (``fetch_crm_result_sets``);
* the by-id customer profile — a single ``WHERE customer_id = …`` snapshot.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from analytics.confluent_sql_client import ConfluentSqlClient
from analytics.lightning_client import LightningClient

logger = logging.getLogger(__name__)

# --- CRM analytics data products ------------------------------------------
#
# Each ``fct_crm_*`` table is a small, pre-aggregated materialized table; the
# live dashboard reads them with five trivial ``SELECT *`` snapshot queries run
# **concurrently** (one ``confluent-sql`` connection per worker — DB-API
# connections are not guaranteed thread-safe). Best-effort: a query that fails
# or raises yields ``[]``/``None`` for its slot, so a partial result still
# renders.

SUMMARY_TABLE = "fct_crm_summary"
BY_SEGMENT_TABLE = "fct_crm_by_segment"
BY_GENERATION_TABLE = "fct_crm_by_generation"
BY_GENDER_TABLE = "fct_crm_by_gender"
BY_COUNTRY_TABLE = "fct_crm_by_country"

_CRM_TABLES = (
    SUMMARY_TABLE,
    BY_SEGMENT_TABLE,
    BY_GENERATION_TABLE,
    BY_GENDER_TABLE,
    BY_COUNTRY_TABLE,
)

_ResultSets = tuple[dict | None, list[dict], list[dict], list[dict], list[dict]]

# --- By-id profile lookup -------------------------------------------------

# The materialized table the by-id snapshot query reads.
PROFILE_TABLE = "fct_c360_profile"

# Columns for the by-id profile lookup.
_PROFILE_COLUMNS = (
    "customer_id", "first_name", "last_name", "customer_segment", "generation_segment",
    "gender", "age_years", "city", "state", "country", "customer_since",
    "days_since_registration", "missing_email_flag", "missing_phone_flag",
    "account_count", "total_balance", "txn_count", "txn_total",
)
# customer_id is an opaque id (UUID-ish); only these characters are ever valid,
# so anything else is rejected before it reaches a SQL literal.
_CUSTOMER_ID_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")


def _sql_str(value: str) -> str:
    """Render a Python string as a single-quoted SQL literal, escaping quotes.

    Doubling embedded single quotes is the standard SQL escape and keeps
    user-supplied search text from breaking out of the literal. LIKE wildcards
    (``%`` / ``_``) in the name are treated literally enough for this demo
    search; a stricter build would ESCAPE them too.
    """
    return "'" + value.replace("'", "''") + "'"


# --- CRM aggregates fetch -------------------------------------------------


def _query_one(client_factory: Callable[[], ConfluentSqlClient], table: str) -> list[dict]:
    """Run one table's snapshot query in its own client; isolate any failure to []."""
    try:
        return client_factory().query(f"SELECT * FROM {table}")
    except Exception as exc:  # noqa: BLE001 — one worker's failure must not sink the rest
        logger.warning("providers: CRM query for %s failed: %s", table, exc, exc_info=True)
        return []


def fetch_crm_result_sets(
    client_factory: Callable[[], ConfluentSqlClient] = ConfluentSqlClient,
) -> _ResultSets:
    """Return ``(summary_row | None, by_segment, by_generation, by_gender, by_country)``.

    Runs the five snapshot queries concurrently. ``summary_row`` is the single
    ``fct_crm_summary`` row (or ``None`` when that query returned nothing).
    """
    with ThreadPoolExecutor(max_workers=len(_CRM_TABLES)) as executor:
        results = dict(
            zip(_CRM_TABLES, executor.map(lambda t: _query_one(client_factory, t), _CRM_TABLES))
        )

    summary_rows = results[SUMMARY_TABLE]
    summary_row = summary_rows[0] if summary_rows else None
    return (
        summary_row,
        results[BY_SEGMENT_TABLE],
        results[BY_GENERATION_TABLE],
        results[BY_GENDER_TABLE],
        results[BY_COUNTRY_TABLE],
    )


# --- By-id profile lookup -------------------------------------------------


def _profile_sql(customer_id: str) -> str:
    # confluent-sql runs in snapshot mode: a WHERE on the primary key returns the
    # single current-state row for this customer, so no LIMIT (and no changelog
    # collapse) is needed.
    cols = ", ".join(_PROFILE_COLUMNS)
    return f"SELECT {cols} FROM {PROFILE_TABLE} WHERE customer_id = {_sql_str(customer_id)}"


def get_customer_profile(customer_id: str) -> tuple[dict | None, str]:
    """Fetch one customer's profile row via a ``WHERE customer_id = …`` query.

    Returns ``(None, "live")`` when the id is malformed or no row matches.
    """
    cid = (customer_id or "").strip()
    if not _CUSTOMER_ID_RE.match(cid):
        return None, "live"
    rows = ConfluentSqlClient().query(_profile_sql(cid))
    return (rows[0] if rows else None), "live"


# --- RTCE / Lightning Query API variant ----------------------------------
#
# Same by-id profile, but served by the Lightning point-lookup API (current
# state directly — no changelog collapse).


def get_customer_profile_rtce(customer_id: str) -> tuple[dict | None, str]:
    """One customer's current-state profile via a Lightning point lookup."""
    cid = (customer_id or "").strip()
    if not _CUSTOMER_ID_RE.match(cid):
        return None, "live"
    rows = LightningClient().query(_profile_sql(cid), _PROFILE_COLUMNS, max_rows=1)
    return (rows[0] if rows else None), "live"
