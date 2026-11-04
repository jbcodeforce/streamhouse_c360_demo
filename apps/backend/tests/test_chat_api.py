"""/api/v1/chat endpoints: the Assistant chat (step 1 stub).

Postgres bootstrap mocked exactly like test_analytics_api.py.
CHAT_FIRST_PROMPT is set to a known value so the welcome test
proves the configured value propagates from backend config to the response.
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
        # — this suite must exercise the stub path only.
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
    assert body["source_mode"] == "stub"


def test_chat_returns_stub_reply_echoing_the_question(client):
    r = client.post("/api/v1/chat", json={"message": "Who is customer 42?"})
    assert r.status_code == 200
    body = r.json()
    assert body["source_mode"] == "stub"
    assert "Who is customer 42?" in body["reply"]


def test_chat_accepts_conversation_history(client):
    r = client.post("/api/v1/chat", json={
        "message": "And their balance?",
        "history": [
            {"role": "user", "content": "Who is customer 42?"},
            {"role": "assistant", "content": "A stub reply."},
        ],
    })
    assert r.status_code == 200
    assert r.json()["source_mode"] == "stub"


def test_chat_requires_a_message(client):
    r = client.post("/api/v1/chat", json={"history": []})
    assert r.status_code == 422
