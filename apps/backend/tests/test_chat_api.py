"""/api/v1/chat endpoints: the Assistant chat.

Postgres bootstrap mocked; tests welcome prompt, unconfigured degradation,
and live agent response routing.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_FIRST_PROMPT = "Hi, Jerome from test"


def _reset_modules() -> None:
    for mod in list(sys.modules):
        if mod in ("config", "main") or mod.startswith(("customers", "api", "chat")):
            del sys.modules[mod]


@pytest.fixture(scope="module")
def client():
    env_patch = patch.dict("os.environ", {
        "CHAT_FIRST_PROMPT": _FIRST_PROMPT,
        # Point at a nonexistent env file so the repo's real .env is never loaded
        "ENV_CONFIG_FILE": "/nonexistent/.env.test-chat",
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


def test_welcome_propagates_configured_prompt(client):
    r = client.get("/api/v1/chat/welcome")
    assert r.status_code == 200
    body = r.json()
    assert body["prompt"] == _FIRST_PROMPT
    assert body["source_mode"] == "live"


def test_chat_unconfigured_returns_error_response(client):
    r = client.post("/api/v1/chat", json={"message": "Who is customer 42?"})
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "error"
    assert "unconfigured" in body["reply"].lower()


def test_chat_with_mocked_agent(client, monkeypatch):
    from chat import agent, service

    monkeypatch.setattr(service, "_live_ready", lambda: True)

    async def fake_run(message, history, session_id=None):
        return f"Customer 42 info for '{message}'"

    monkeypatch.setattr(agent, "run_agent", fake_run)

    r = client.post("/api/v1/chat", json={"message": "Who is customer 42?"})
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "live"
    assert "Customer 42 info" in body["reply"]


def test_chat_accepts_conversation_history(client, monkeypatch):
    from chat import agent, service

    monkeypatch.setattr(service, "_live_ready", lambda: True)

    async def fake_run(message, history, session_id=None):
        return "Balance is $1000."

    monkeypatch.setattr(agent, "run_agent", fake_run)

    r = client.post("/api/v1/chat", json={
        "message": "And their balance?",
        "history": [
            {"role": "user", "content": "Who is customer 42?"},
            {"role": "assistant", "content": "Jane Doe"},
        ],
    })
    assert r.status_code == 200
    assert r.json()["source_mode"] == "live"
    assert r.json()["reply"] == "Balance is $1000."


def test_chat_requires_a_message(client):
    r = client.post("/api/v1/chat", json={"history": []})
    assert r.status_code == 422
