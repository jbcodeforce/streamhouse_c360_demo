"""Integration tests for the Customers REST API — SINK=postgres.

These tests require a live PostgreSQL instance.  They are automatically
skipped when DATABASE_URL is not available.

To run locally:
    1. Start the container:  ./apps/backend/start_local_pg_server.sh
    2. From apps/backend/:   uv run pytest tests/test_customers_postgres.py -v

Seam: HTTP API at /api/v1/customers
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_create_payload, make_full_payload


# ---------------------------------------------------------------------------
# App fixture — SINK=postgres, uses DATABASE_URL from .env.local / environment
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=False)
def client():
    """TestClient wired to SINK=postgres.

    Overrides the live settings singleton and db_sink pool directly so the
    suite runs cleanly after a kafka suite in the same process.
    Automatically skipped when DATABASE_URL is not set.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping postgres integration test")

    # Import everything fresh (modules may already be loaded from kafka suite)
    import config
    import db
    import customers.kafka_producer as kafka_producer
    import main  # noqa: PLC0415

    # Directly override the settings singleton for the duration of this suite
    original_sink = config.settings.SINK
    original_db_url = config.settings.DATABASE_URL
    config.settings.SINK = "postgres"
    config.settings.DATABASE_URL = database_url

    # Reset the shared connection pool so it re-connects with the correct URL
    def _reset_pool():
        if db._pool is not None:
            try:
                db._pool.closeall()
            except Exception:
                pass
            db._pool = None

    _reset_pool()

    with TestClient(main.app) as test_client:
        yield test_client

    # Restore settings
    config.settings.SINK = original_sink
    config.settings.DATABASE_URL = original_db_url
    _reset_pool()


# ---------------------------------------------------------------------------
# Teardown tracker — collects every customer_id created during the suite and
# deletes them all after the module finishes, leaving the seed rows intact.
# ---------------------------------------------------------------------------

_created_ids: list[str] = []


@pytest.fixture(autouse=True)
def _track_created(client):
    """After each test, delete any customers that were newly created."""
    before = {c["customer_id"] for c in client.get("/api/v1/customers").json()}
    yield
    after = {c["customer_id"] for c in client.get("/api/v1/customers").json()}
    for cid in after - before:
        client.delete(f"/api/v1/customers/{cid}")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_reports_postgres_sink(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["sink"] == "postgres"


# ---------------------------------------------------------------------------
# GET /api/v1/customers  (list)
# ---------------------------------------------------------------------------

class TestListCustomers:
    def test_returns_200(self, client):
        resp = client.get("/api/v1/customers")
        assert resp.status_code == 200

    def test_returns_seed_customers_after_bootstrap(self, client):
        """The 10 CSV seed rows should have been inserted during lifespan startup."""
        customers = client.get("/api/v1/customers").json()
        assert len(customers) >= 10

    def test_each_customer_has_required_fields(self, client):
        customers = client.get("/api/v1/customers").json()
        for c in customers:
            assert "customer_id" in c
            assert "email" in c
            assert "created_at" in c


# ---------------------------------------------------------------------------
# POST /api/v1/customers  (create)
# ---------------------------------------------------------------------------

class TestCreateCustomer:
    def test_returns_201(self, client):
        resp = client.post("/api/v1/customers", json=make_create_payload())
        assert resp.status_code == 201

    def test_response_contains_generated_id(self, client):
        body = client.post("/api/v1/customers", json=make_create_payload()).json()
        assert "customer_id" in body
        assert body["customer_id"] is not None

    def test_response_echoes_submitted_fields(self, client):
        payload = make_create_payload(
            first_name="Diana",
            last_name="Prince",
            segment="ENTERPRISE",
        )
        body = client.post("/api/v1/customers", json=payload).json()
        assert body["first_name"] == "Diana"
        assert body["last_name"] == "Prince"
        assert body["segment"] == "ENTERPRISE"

    def test_created_customer_is_retrievable(self, client):
        payload = make_create_payload(first_name="Eve", last_name="Adams")
        created = client.post("/api/v1/customers", json=payload).json()

        retrieved = client.get(f"/api/v1/customers/{created['customer_id']}").json()
        assert retrieved["customer_id"] == created["customer_id"]
        assert retrieved["first_name"] == "Eve"

    def test_created_customer_appears_in_list(self, client):
        created = client.post("/api/v1/customers", json=make_create_payload()).json()
        all_ids = [c["customer_id"] for c in client.get("/api/v1/customers").json()]
        assert created["customer_id"] in all_ids

    def test_missing_required_field_returns_422(self, client):
        resp = client.post("/api/v1/customers", json={"first_name": "No", "last_name": "Email"})
        assert resp.status_code == 422

    def test_duplicate_email_returns_409(self, client):
        email = make_create_payload()["email"]
        client.post("/api/v1/customers", json=make_create_payload(email=email))
        resp = client.post("/api/v1/customers", json=make_create_payload(email=email))
        assert resp.status_code == 409

    def test_full_payload_all_optional_fields_persisted(self, client):
        payload = make_full_payload(first_name="Frank", last_name="Castle")
        body = client.post("/api/v1/customers", json=payload).json()
        assert body["phone"] == "555-000-1234"
        assert body["city"] == "Testville"
        assert body["segment"] == "PRIVATE"


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_id}  (read one)
# ---------------------------------------------------------------------------

class TestGetCustomer:
    def test_returns_200_for_existing_customer(self, client):
        seed_id = client.get("/api/v1/customers").json()[0]["customer_id"]
        resp = client.get(f"/api/v1/customers/{seed_id}")
        assert resp.status_code == 200

    def test_returns_correct_customer_data(self, client):
        all_customers = client.get("/api/v1/customers").json()
        target = all_customers[0]
        resp = client.get(f"/api/v1/customers/{target['customer_id']}")
        assert resp.json()["email"] == target["email"]

    def test_returns_404_for_unknown_id(self, client):
        resp = client.get("/api/v1/customers/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_invalid_uuid_returns_422(self, client):
        resp = client.get("/api/v1/customers/not-a-uuid")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/v1/customers/{customer_id}  (update)
# ---------------------------------------------------------------------------

class TestUpdateCustomer:
    def _create(self, client) -> dict:
        return client.post("/api/v1/customers", json=make_create_payload(
            first_name="PG",
            last_name="Original",
            city="OriginalCity",
        )).json()

    def test_returns_200(self, client):
        customer = self._create(client)
        resp = client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"first_name": "PGUpdated"},
        )
        assert resp.status_code == 200

    def test_updated_field_is_changed(self, client):
        customer = self._create(client)
        resp = client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"first_name": "Changed"},
        )
        assert resp.json()["first_name"] == "Changed"

    def test_non_updated_fields_are_preserved(self, client):
        customer = self._create(client)
        resp = client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"segment": "SMB"},
        )
        body = resp.json()
        assert body["last_name"] == "Original"
        assert body["city"] == "OriginalCity"
        assert body["segment"] == "SMB"

    def test_update_is_visible_on_subsequent_get(self, client):
        customer = self._create(client)
        client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"status": "INACTIVE"},
        )
        retrieved = client.get(f"/api/v1/customers/{customer['customer_id']}").json()
        assert retrieved["status"] == "INACTIVE"

    def test_updated_at_is_refreshed(self, client):
        """updated_at must change after a PUT (the DB trigger handles this)."""
        customer = self._create(client)
        original_updated_at = customer["updated_at"]

        import time; time.sleep(0.01)  # ensure timestamp advances
        updated = client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"first_name": "Timestamped"},
        ).json()
        assert updated["updated_at"] != original_updated_at

    def test_returns_404_for_unknown_id(self, client):
        resp = client.put(
            "/api/v1/customers/00000000-0000-0000-0000-000000000000",
            json={"first_name": "Ghost"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/customers/{customer_id}
# ---------------------------------------------------------------------------

class TestDeleteCustomer:
    def _create(self, client) -> dict:
        return client.post("/api/v1/customers", json=make_create_payload(
            first_name="To", last_name="Delete",
        )).json()

    def test_returns_204(self, client):
        customer = self._create(client)
        resp = client.delete(f"/api/v1/customers/{customer['customer_id']}")
        assert resp.status_code == 204

    def test_deleted_customer_is_no_longer_retrievable(self, client):
        customer = self._create(client)
        client.delete(f"/api/v1/customers/{customer['customer_id']}")
        resp = client.get(f"/api/v1/customers/{customer['customer_id']}")
        assert resp.status_code == 404

    def test_deleted_customer_does_not_appear_in_list(self, client):
        customer = self._create(client)
        client.delete(f"/api/v1/customers/{customer['customer_id']}")
        all_ids = [c["customer_id"] for c in client.get("/api/v1/customers").json()]
        assert customer["customer_id"] not in all_ids

    def test_returns_404_for_unknown_id(self, client):
        resp = client.delete("/api/v1/customers/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
