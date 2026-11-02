"""Shared pytest fixtures for the C360 backend integration tests.

Two test suites coexist:

* **Kafka suite** (``test_customers_kafka.py``) — zero infrastructure required.
  Runs with ``SINK=kafka``; Kafka/SR calls are mocked at the boundary.

* **Postgres suite** (``test_customers_postgres.py``) — requires a live
  PostgreSQL instance.  The suite is automatically skipped when
  ``DATABASE_URL`` is not set in the environment or in ``.env.local``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env.local if present (local container credentials)
# ---------------------------------------------------------------------------
_env_local = Path(__file__).parent.parent / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local, override=False)

_BACKEND_DIR = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Isolate the seed CSVs: tests mutate throwaway copies, never the committed
# seed files. The inventory modules read these env vars at call time, so the
# override is in effect before any app lifespan or test-created client loads.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def isolate_seed_csvs(tmp_path_factory):
    """Point the CSV-backed inventories at per-session copies of the seeds."""
    tmp = tmp_path_factory.mktemp("seed_csvs")
    seeds = {
        "CUSTOMERS_CSV_PATH": _BACKEND_DIR / "customers" / "data" / "customers.csv",
        "ACCOUNTS_CSV_PATH": _BACKEND_DIR / "accounts" / "data" / "accounts.csv",
        "TRANSACTIONS_CSV_PATH": _BACKEND_DIR / "transactions" / "data" / "transactions.csv",
    }
    previous = {}
    for env_key, src in seeds.items():
        dst = tmp / src.name
        shutil.copy(src, dst)
        previous[env_key] = os.environ.get(env_key)
        os.environ[env_key] = str(dst)
    yield
    for env_key, prior in previous.items():
        if prior is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = prior


# ---------------------------------------------------------------------------
# Shared payload factories
# ---------------------------------------------------------------------------

def make_create_payload(**overrides) -> dict:
    """Return a minimal valid CustomerCreate payload."""
    base = {
        "first_name": "Test",
        "last_name": "User",
        "email": f"test.user.{os.urandom(4).hex()}@example.com",
        "country": "US",
        "status": "ACTIVE",
    }
    base.update(overrides)
    return base


def make_full_payload(**overrides) -> dict:
    """Return a CustomerCreate payload with all optional fields populated."""
    base = make_create_payload(
        phone="555-000-1234",
        gender="M",
        address_line1="1 Test St",
        city="Testville",
        state="CA",
        postal_code="90210",
        segment="PRIVATE",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Marker: skip postgres tests when DATABASE_URL is absent
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_postgres: skip if DATABASE_URL is not configured",
    )


@pytest.fixture(autouse=False)
def skip_without_postgres():
    """Skip the test if DATABASE_URL is not available."""
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — skipping postgres integration test")
