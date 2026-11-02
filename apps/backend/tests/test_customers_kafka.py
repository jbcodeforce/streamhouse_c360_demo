"""Integration tests for the Customers REST API — SINK=kafka (no infra required).

The Kafka producer is mocked at the system boundary (confluent produce call).
All reads and writes go through the in-memory CSV inventory, so these tests
run anywhere without a running database or Kafka cluster.

Seam: HTTP API at /api/v1/customers
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_create_payload, make_full_payload

# ---------------------------------------------------------------------------
# App fixture — force SINK=kafka before importing main so Settings picks it up
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mocks():
    """MagicMock objects for the three kafka_producer boundary functions."""
    return {
        "produce_create": MagicMock(),
        "produce_update": MagicMock(),
        "produce_delete": MagicMock(),
    }


@pytest.fixture(scope="module")
def client(mocks):
    """TestClient wired to SINK=kafka with Kafka produces mocked out."""
    env_patch = patch.dict("os.environ", {
        "SINK": "kafka",
        # Isolate from the repo's real .env so app startup never attempts a real
        # connection (it may point at live/remote infra or enable seeding).
        "ENV_CONFIG_FILE": "/nonexistent/.env.test",
        "KAFKA_SEED_ON_START": "false",
        "KAFKA_BOOTSTRAP_SERVERS": "mock:9092",
        "SCHEMA_REGISTRY_URL": "http://mock-sr",
        "SCHEMA_REGISTRY_API_KEY": "key",
        "SCHEMA_REGISTRY_API_SECRET": "secret",
    })
    env_patch.start()

    # Force re-import of config so Settings re-reads the patched env
    for mod in list(sys.modules.keys()):
        if mod in ("config", "customers.service", "customers.kafka_producer",
                   "customers.inventory", "main"):
            del sys.modules[mod]

    # Mock kafka_producer at the boundary — we don't want real Confluent calls
    with patch("customers.kafka_producer.produce_create", mocks["produce_create"]), \
         patch("customers.kafka_producer.produce_update", mocks["produce_update"]), \
         patch("customers.kafka_producer.produce_delete", mocks["produce_delete"]):

        import main  # noqa: PLC0415 — intentional late import after env patch
        with TestClient(main.app) as test_client:
            yield test_client

    env_patch.stop()


# ---------------------------------------------------------------------------
# Helper — extract the Customer arg passed to a produce_* mock call
# ---------------------------------------------------------------------------

def _last_produce_arg(mock: MagicMock):
    """Return the Customer positional arg from the most recent mock call."""
    return mock.call_args[0][0]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_reports_kafka_sink(self, client):
        resp = client.get("/health")
        assert resp.json()["sink"] == "kafka"


# ---------------------------------------------------------------------------
# GET /api/v1/customers  (list)
# ---------------------------------------------------------------------------

class TestListCustomers:
    def test_returns_200(self, client):
        resp = client.get("/api/v1/customers")
        assert resp.status_code == 200

    def test_returns_seed_customers(self, client):
        """The 10 CSV seed rows are loaded on startup."""
        resp = client.get("/api/v1/customers")
        assert len(resp.json()) >= 10

    def test_each_customer_has_required_fields(self, client):
        customers = client.get("/api/v1/customers").json()
        for c in customers:
            assert "customer_id" in c
            assert "first_name" in c
            assert "last_name" in c
            assert "email" in c


# ---------------------------------------------------------------------------
# POST /api/v1/customers  (create)
# ---------------------------------------------------------------------------

class TestCreateCustomer:
    def test_returns_201(self, client, mocks):
        resp = client.post("/api/v1/customers", json=make_create_payload())
        assert resp.status_code == 201

    def test_response_contains_generated_id(self, client, mocks):
        resp = client.post("/api/v1/customers", json=make_create_payload())
        body = resp.json()
        assert "customer_id" in body
        assert body["customer_id"] is not None

    def test_response_echoes_submitted_fields(self, client, mocks):
        payload = make_create_payload(
            first_name="Alice",
            last_name="Smith",
            segment="SMB",
        )
        body = client.post("/api/v1/customers", json=payload).json()
        assert body["first_name"] == "Alice"
        assert body["last_name"] == "Smith"
        assert body["segment"] == "SMB"

    def test_created_customer_is_retrievable(self, client, mocks):
        payload = make_create_payload(first_name="Bob", last_name="Jones")
        created = client.post("/api/v1/customers", json=payload).json()

        retrieved = client.get(f"/api/v1/customers/{created['customer_id']}").json()
        assert retrieved["customer_id"] == created["customer_id"]
        assert retrieved["first_name"] == "Bob"

    def test_created_customer_appears_in_list(self, client, mocks):
        payload = make_create_payload()
        created = client.post("/api/v1/customers", json=payload).json()

        all_ids = [c["customer_id"] for c in client.get("/api/v1/customers").json()]
        assert created["customer_id"] in all_ids

    def test_missing_required_field_returns_422(self, client, mocks):
        resp = client.post("/api/v1/customers", json={"first_name": "No", "last_name": "Email"})
        assert resp.status_code == 422

    def test_full_payload_all_fields_persisted(self, client, mocks):
        payload = make_full_payload(first_name="Carol", last_name="White")
        body = client.post("/api/v1/customers", json=payload).json()
        assert body["phone"] == "555-000-1234"
        assert body["city"] == "Testville"
        assert body["segment"] == "PRIVATE"

    # ── Debezium envelope assertions ────────────────────────────────────────

    def test_produce_create_is_called_once(self, client, mocks):
        mocks["produce_create"].reset_mock()
        client.post("/api/v1/customers", json=make_create_payload())
        mocks["produce_create"].assert_called_once()

    def test_produce_create_receives_correct_customer(self, client, mocks):
        mocks["produce_create"].reset_mock()
        payload = make_create_payload(first_name="Debezium", last_name="Test")
        created = client.post("/api/v1/customers", json=payload).json()

        customer_arg = _last_produce_arg(mocks["produce_create"])
        assert str(customer_arg.customer_id) == created["customer_id"]
        assert customer_arg.first_name == "Debezium"


# ---------------------------------------------------------------------------
# GET /api/v1/customers/{customer_id}  (read one)
# ---------------------------------------------------------------------------

class TestGetCustomer:
    def test_returns_200_for_seed_customer(self, client):
        seed_id = client.get("/api/v1/customers").json()[0]["customer_id"]
        resp = client.get(f"/api/v1/customers/{seed_id}")
        assert resp.status_code == 200

    def test_returns_correct_customer(self, client):
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
            first_name="Update",
            last_name="Me",
        )).json()

    def test_returns_200(self, client, mocks):
        customer = self._create(client)
        resp = client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"first_name": "Updated"},
        )
        assert resp.status_code == 200

    def test_updated_field_is_changed(self, client, mocks):
        customer = self._create(client)
        resp = client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"first_name": "Changed"},
        )
        assert resp.json()["first_name"] == "Changed"

    def test_non_updated_fields_are_preserved(self, client, mocks):
        customer = self._create(client)
        resp = client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"city": "NewCity"},
        )
        body = resp.json()
        assert body["last_name"] == "Me"
        assert body["city"] == "NewCity"

    def test_update_is_visible_on_subsequent_get(self, client, mocks):
        customer = self._create(client)
        client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"segment": "ENTERPRISE"},
        )
        retrieved = client.get(f"/api/v1/customers/{customer['customer_id']}").json()
        assert retrieved["segment"] == "ENTERPRISE"

    def test_returns_404_for_unknown_id(self, client, mocks):
        resp = client.put(
            "/api/v1/customers/00000000-0000-0000-0000-000000000000",
            json={"first_name": "Ghost"},
        )
        assert resp.status_code == 404

    # ── Debezium envelope assertions ────────────────────────────────────────

    def test_produce_update_is_called_once(self, client, mocks):
        customer = self._create(client)
        mocks["produce_update"].reset_mock()
        client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"status": "INACTIVE"},
        )
        mocks["produce_update"].assert_called_once()

    def test_produce_update_receives_updated_customer(self, client, mocks):
        customer = self._create(client)
        mocks["produce_update"].reset_mock()
        client.put(
            f"/api/v1/customers/{customer['customer_id']}",
            json={"segment": "SMB"},
        )
        customer_arg = _last_produce_arg(mocks["produce_update"])
        assert str(customer_arg.customer_id) == customer["customer_id"]
        assert customer_arg.segment == "SMB"


# ---------------------------------------------------------------------------
# DELETE /api/v1/customers/{customer_id}
# ---------------------------------------------------------------------------

class TestDeleteCustomer:
    def _create(self, client) -> dict:
        return client.post("/api/v1/customers", json=make_create_payload(
            first_name="To", last_name="Delete",
        )).json()

    def test_returns_204(self, client, mocks):
        customer = self._create(client)
        resp = client.delete(f"/api/v1/customers/{customer['customer_id']}")
        assert resp.status_code == 204

    def test_deleted_customer_is_no_longer_retrievable(self, client, mocks):
        customer = self._create(client)
        client.delete(f"/api/v1/customers/{customer['customer_id']}")
        resp = client.get(f"/api/v1/customers/{customer['customer_id']}")
        assert resp.status_code == 404

    def test_deleted_customer_does_not_appear_in_list(self, client, mocks):
        customer = self._create(client)
        client.delete(f"/api/v1/customers/{customer['customer_id']}")
        all_ids = [c["customer_id"] for c in client.get("/api/v1/customers").json()]
        assert customer["customer_id"] not in all_ids

    def test_returns_404_for_unknown_id(self, client, mocks):
        resp = client.delete("/api/v1/customers/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    # ── Debezium envelope assertions ────────────────────────────────────────

    def test_produce_delete_is_called_once(self, client, mocks):
        customer = self._create(client)
        mocks["produce_delete"].reset_mock()
        client.delete(f"/api/v1/customers/{customer['customer_id']}")
        mocks["produce_delete"].assert_called_once()

    def test_produce_delete_receives_correct_customer(self, client, mocks):
        customer = self._create(client)
        mocks["produce_delete"].reset_mock()
        client.delete(f"/api/v1/customers/{customer['customer_id']}")
        customer_arg = _last_produce_arg(mocks["produce_delete"])
        assert str(customer_arg.customer_id) == customer["customer_id"]


# ---------------------------------------------------------------------------
# Debezium envelope unit tests — verify _build_envelope output shape
# ---------------------------------------------------------------------------

class TestDebeziumEnvelope:
    """Unit tests for the envelope builder — no HTTP, no Kafka."""

    def _make_customer(self):
        from datetime import datetime, date, timezone
        from uuid import uuid4
        from customers.models import Customer
        return Customer(
            customer_id=uuid4(),
            first_name="Env",
            last_name="Test",
            email="env@test.com",
            country="US",
            customer_since=datetime(2024, 1, 15, tzinfo=timezone.utc),
            status="ACTIVE",
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )

    def test_create_envelope_has_null_before_and_value_after(self):
        from customers.kafka_producer import _build_envelope, _OP_CREATE
        c = self._make_customer()
        env = _build_envelope(c, _OP_CREATE)
        assert env["before"] is None
        assert env["after"] is not None
        assert env["op"] == "c"

    def test_update_envelope_has_null_before_and_value_after(self):
        from customers.kafka_producer import _build_envelope, _OP_UPDATE
        c = self._make_customer()
        env = _build_envelope(c, _OP_UPDATE)
        assert env["before"] is None
        assert env["after"] is not None
        assert env["op"] == "u"

    def test_delete_envelope_has_value_before_and_null_after(self):
        from customers.kafka_producer import _build_envelope, _OP_DELETE
        c = self._make_customer()
        env = _build_envelope(c, _OP_DELETE)
        assert env["before"] is not None
        assert env["after"] is None
        assert env["op"] == "d"

    def test_envelope_source_block_is_present(self):
        from customers.kafka_producer import _build_envelope, _OP_CREATE
        env = _build_envelope(self._make_customer(), _OP_CREATE)
        src = env["source"]
        assert src["db"] == "c360db"
        assert src["schema"] == "public"
        assert src["table"] == "customers"

    def test_customer_since_is_debezium_zoned_timestamp(self):
        from customers.kafka_producer import _build_value
        c = self._make_customer()
        value = _build_value(c)
        assert value["customer_since"] == "2024-01-15T00:00:00.000000Z"

    def test_created_at_is_debezium_zoned_timestamp(self):
        from customers.kafka_producer import _build_value
        c = self._make_customer()
        value = _build_value(c)
        assert value["created_at"] == "2024-01-15T10:30:00.000000Z"

    def test_date_of_birth_none_produces_null(self):
        from customers.kafka_producer import _build_value
        c = self._make_customer()
        assert c.date_of_birth is None
        value = _build_value(c)
        assert value["date_of_birth"] is None


# ---------------------------------------------------------------------------
# get_by_name tests
# ---------------------------------------------------------------------------

class TestGetByName:
    def test_get_by_name_exact_and_partial(self, client):
        from customers import service
        matches = service.get_by_name("Sharma")
        assert len(matches) > 0
        assert any(c.last_name == "Sharma" for c in matches)

    def test_get_by_name_case_insensitive(self, client):
        from customers import service
        matches = service.get_by_name("sharma")
        assert len(matches) > 0
        assert any(c.last_name == "Sharma" for c in matches)

    def test_get_by_name_full_name(self, client):
        from customers import service
        matches = service.get_by_name("Linda Sharma")
        assert len(matches) > 0
        assert any(c.first_name == "Linda" and c.last_name == "Sharma" for c in matches)

    def test_get_by_name_empty_or_whitespace_returns_empty(self, client):
        from customers import service
        assert service.get_by_name("") == []
        assert service.get_by_name("   ") == []

    def test_get_by_name_no_match(self, client):
        from customers import service
        assert service.get_by_name("NonExistentCustomerNameXYZ") == []

    def test_list_endpoint_name_filter_searches(self, client):
        # The dashboard resolves a name here (system of record) before calling
        # the analytics by-id profile endpoint.
        r = client.get("/api/v1/customers", params={"name": "Sharma"})
        assert r.status_code == 200
        body = r.json()
        assert len(body) > 0
        assert all("Sharma" in c["last_name"] or "Sharma" in c["first_name"] for c in body)

    def test_list_endpoint_blank_name_returns_empty(self, client):
        r = client.get("/api/v1/customers", params={"name": "   "})
        assert r.status_code == 200 and r.json() == []

    def test_list_endpoint_without_name_lists_all(self, client):
        r = client.get("/api/v1/customers")
        assert r.status_code == 200 and len(r.json()) > 0
