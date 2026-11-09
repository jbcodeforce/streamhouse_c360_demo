"""Unit tests for chat.service orchestration and graceful degradation.

These exercise the async orchestrator directly (no TestClient) with config
patched on the settings singleton and the agno agent monkeypatched — so the
live, missing-config, and agent-failure paths are all covered with no LLM
or MCP infrastructure.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

import config
from chat import agent as chat_agent
from chat import service
from chat.models import ChatMessage, ChatRequest


@pytest.fixture(autouse=True)
def _consistent_modules():
    """Keep the test, the service, and config pointing at the SAME modules.

    Other suites (e.g. test_chat_api) reset ``sys.modules`` on teardown. When this
    file runs after them, the service re-imports fresh ``config``/``chat.agent``
    objects at call time while our module-level references still point at the
    pre-reset ones — so monkeypatches and settings land on the wrong objects and
    the real agent runs. Re-resolving against current ``sys.modules`` here (and
    clearing the session cache) makes the patches take effect regardless of order.
    """
    global config, chat_agent, service, ChatMessage, ChatRequest
    config = importlib.import_module("config")
    chat_agent = importlib.import_module("chat.agent")
    service = importlib.import_module("chat.service")
    models = importlib.import_module("chat.models")
    ChatMessage = models.ChatMessage
    ChatRequest = models.ChatRequest
    chat_agent._sessions.clear()
    yield
    chat_agent._sessions.clear()


# The MCP URL is derived from the Confluent coordinates, so live config means
# those five fields plus the LLM and GLOBAL credentials.
_LIVE_ENV = {
    "LLM_BASE_URL": "http://127.0.0.1:7999/v1",
    "LLM_MODEL": "Ornith-1.5-9B-MLX-8bit",
    "CLOUD_REGION": "us-west-2",
    "CLOUD_PROVIDER": "aws",
    "FLINK_ORG_ID": "org-123",
    "FLINK_ENV_ID": "env-123",
    "KAFKA_CLUSTER_ID": "lkc-123",
    "CONFLUENT_GLOBAL_KEY": "gkey",
    "CONFLUENT_GLOBAL_SECRET": "gsecret",
}


def _set_live(monkeypatch) -> None:
    for key, value in _LIVE_ENV.items():
        monkeypatch.setattr(config.settings, key, value)


def test_rtce_mcp_url_is_derived_from_coordinates(monkeypatch):
    for key in ("CLOUD_REGION", "CLOUD_PROVIDER", "FLINK_ORG_ID", "FLINK_ENV_ID", "KAFKA_CLUSTER_ID"):
        monkeypatch.setattr(config.settings, key, _LIVE_ENV[key])
    assert config.settings.rtce_mcp_url() == (
        "https://mcp.us-west-2.aws.confluent.cloud/mcp/v1/context-engine/"
        "organizations/org-123/environments/env-123/kafka-clusters/lkc-123"
    )


def test_rtce_mcp_url_is_none_when_a_coordinate_is_missing(monkeypatch):
    for key in ("CLOUD_REGION", "CLOUD_PROVIDER", "FLINK_ORG_ID", "FLINK_ENV_ID", "KAFKA_CLUSTER_ID"):
        monkeypatch.setattr(config.settings, key, _LIVE_ENV[key])
    monkeypatch.setattr(config.settings, "FLINK_ENV_ID", None)
    assert config.settings.rtce_mcp_url() is None


def test_unconfigured_chat_returns_error_response(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_BASE_URL", None)
    resp = asyncio.run(service.get_reply(ChatRequest(message="Who is customer 42?")))
    assert resp.source_mode == "error"
    assert "unconfigured" in resp.reply.lower()


def test_missing_coordinate_returns_unconfigured_error(monkeypatch):
    _set_live(monkeypatch)
    monkeypatch.setattr(config.settings, "KAFKA_CLUSTER_ID", None)  # URL can't be derived
    resp = asyncio.run(service.get_reply(ChatRequest(message="hello")))
    assert resp.source_mode == "error"
    assert "unconfigured" in resp.reply.lower()


def test_live_runs_the_agent(monkeypatch):
    _set_live(monkeypatch)

    captured = {}

    async def fake_run(message, history, session_id=None):
        captured["message"] = message
        captured["history"] = history
        captured["session_id"] = session_id
        return "Customer 42 is Jane Doe, RETAIL segment."

    monkeypatch.setattr(chat_agent, "run_agent", fake_run)

    resp = asyncio.run(service.get_reply(ChatRequest(
        message="Who is customer 42?",
        history=[ChatMessage(role="user", content="hi")],
        session_id="sess-abc",
    )))
    assert resp.source_mode == "live"
    assert resp.reply == "Customer 42 is Jane Doe, RETAIL segment."
    assert resp.session_id == "sess-abc"
    assert captured["message"] == "Who is customer 42?"
    assert captured["history"] == [ChatMessage(role="user", content="hi")]
    assert captured["session_id"] == "sess-abc"


def test_live_agent_failure_returns_error_mode(monkeypatch):
    _set_live(monkeypatch)

    async def boom(message, history, session_id=None):
        raise RuntimeError("MCP unreachable")

    monkeypatch.setattr(chat_agent, "run_agent", boom)

    resp = asyncio.run(service.get_reply(ChatRequest(message="anything")))
    assert resp.source_mode == "error"
    assert "assistant backend" in resp.reply.lower()


def test_live_empty_answer_is_replaced(monkeypatch):
    _set_live(monkeypatch)

    async def empty(message, history, session_id=None):
        return ""

    monkeypatch.setattr(chat_agent, "run_agent", empty)

    resp = asyncio.run(service.get_reply(ChatRequest(message="anything")))
    assert resp.source_mode == "live"
    assert resp.reply == "(no answer)"


def test_live_turn_is_produced_to_agent_conversations(monkeypatch):
    _set_live(monkeypatch)
    monkeypatch.setattr(config.settings, "LLM_MODEL", "Ornith-1.5-9B-MLX-8bit")

    async def fake_run(message, history, session_id=None):
        return "Customer 42 is Jane Doe, RETAIL segment."

    monkeypatch.setattr(chat_agent, "run_agent", fake_run)

    from chat import conversation_producer
    calls = []
    monkeypatch.setattr(
        conversation_producer, "produce_turn",
        lambda session_id, request_text, response_text, **kw: calls.append(
            (session_id, request_text, response_text, kw)
        ),
    )

    asyncio.run(service.get_reply(ChatRequest(
        message="Who is customer 42?", session_id="sess-abc",
    )))

    assert len(calls) == 1
    session_id, request_text, response_text, kw = calls[0]
    assert session_id == "sess-abc"
    assert request_text == "Who is customer 42?"
    assert response_text == "Customer 42 is Jane Doe, RETAIL segment."
    assert kw["model"] == "Ornith-1.5-9B-MLX-8bit"
    assert kw["source_mode"] == "live"


def test_unconfigured_turn_is_not_produced(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_BASE_URL", None)

    from chat import conversation_producer
    calls = []
    monkeypatch.setattr(
        conversation_producer, "produce_turn",
        lambda *a, **k: calls.append((a, k)),
    )

    asyncio.run(service.get_reply(ChatRequest(message="hello", session_id="s")))
    assert calls == []


def test_agent_failure_produces_no_turn(monkeypatch):
    _set_live(monkeypatch)

    async def boom(message, history, session_id=None):
        raise RuntimeError("MCP unreachable")

    monkeypatch.setattr(chat_agent, "run_agent", boom)

    from chat import conversation_producer
    calls = []
    monkeypatch.setattr(
        conversation_producer, "produce_turn",
        lambda *a, **k: calls.append((a, k)),
    )

    resp = asyncio.run(service.get_reply(ChatRequest(message="anything")))
    assert resp.source_mode == "error"
    assert calls == []


def test_reset_session_delegates_to_agent(monkeypatch):
    seen = {}

    async def fake_reset(session_id):
        seen["session_id"] = session_id
        return True

    monkeypatch.setattr(chat_agent, "reset_session", fake_reset)
    assert asyncio.run(service.reset_session("sess-xyz")) is True
    assert seen["session_id"] == "sess-xyz"
