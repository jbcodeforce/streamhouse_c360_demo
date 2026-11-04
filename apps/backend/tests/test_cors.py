"""CORS must allow the Vite dev origin.

Postgres bootstrap is mocked (no infra). The fixture fully resets the imported
app modules in sys.modules on teardown so suites that reimport ``main``
afterwards start from a clean module graph.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

DEV_ORIGIN = "http://localhost:5173"


def _reset_modules() -> None:
    """Drop the app's modules AND their packages from sys.modules.

    Popping a submodule (e.g. ``customers.service``) alone leaves a stale
    attribute on the cached ``customers`` package object, so a later
    ``from customers import service`` returns the old module instead of
    reimporting. Clearing the packages too forces a clean reimport for
    suites that run after this one (e.g. test_customers_kafka).
    """
    for mod in list(sys.modules):
        if mod in ("config", "main") or mod.startswith(("customers", "api")):
            del sys.modules[mod]


@pytest.fixture(scope="module")
def client():
    env_patch = patch.dict("os.environ", {
        # Isolate from the repo's real .env so app startup never attempts a real
        # connection (it may point at live/remote infra or enable seeding).
        "ENV_CONFIG_FILE": "/nonexistent/.env.test",
        "KAFKA_BOOTSTRAP_SERVERS": "mock:9092",
        "SCHEMA_REGISTRY_URL": "http://mock-sr",
        "SCHEMA_REGISTRY_API_KEY": "key",
        "SCHEMA_REGISTRY_API_SECRET": "secret",
    })
    env_patch.start()
    _reset_modules()

    with patch("bootstrap.init_and_seed"):
        import main  # noqa: PLC0415 — intentional late import after env patch
        with TestClient(main.app) as test_client:
            yield test_client

    env_patch.stop()
    _reset_modules()


def test_cors_allows_dev_origin(client):
    resp = client.get("/health", headers={"Origin": DEV_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == DEV_ORIGIN


def test_cors_preflight_for_customers(client):
    resp = client.options(
        "/api/v1/customers",
        headers={
            "Origin": DEV_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == DEV_ORIGIN
