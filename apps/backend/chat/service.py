"""Orchestration for the Assistant chat.

Backed by an agno agent (``chat.agent``) wired to a local LLM + the RTCE
context-engine MCP server.

Robustness mirrors the analytics resource: never raise to the caller. A
request with missing LLM/MCP config returns an unconfigured error response; an
agent failure returns a friendly error reply. ``source_mode`` labels the outcome
("live" | "error") so the UI/tests can tell.

Config is read via a late ``import config`` so tests that patch settings take
effect here.
"""

from __future__ import annotations

import logging

import config
from chat.models import ChatRequest, ChatResponse, WelcomeResponse

logger = logging.getLogger("c360.chat")


def get_welcome() -> WelcomeResponse:
    """Return the empty-state greeting from ``CHAT_FIRST_PROMPT``."""
    return WelcomeResponse(prompt=config.settings.CHAT_FIRST_PROMPT, source_mode="live")


def _live_ready() -> bool:
    """True when the LLM, MCP, and Confluent config is complete."""
    s = config.settings
    return bool(
        s.LLM_BASE_URL
        and s.LLM_MODEL
        and s.rtce_mcp_url()
        and s.CONFLUENT_GLOBAL_KEY
        and s.CONFLUENT_GLOBAL_SECRET
    )


async def get_reply(request: ChatRequest) -> ChatResponse:
    """Answer a user question, degrading gracefully instead of raising."""
    message = request.message.strip()
    session_id = request.session_id

    if not _live_ready():
        return ChatResponse(
            reply="The assistant is unconfigured. Please configure LLM and RTCE context-engine credentials.",
            source_mode="error",
            session_id=session_id,
        )

    try:
        from chat import agent  # late import: only load agno on the live path

        reply = await agent.run_agent(message, request.history, session_id)
        answer = reply or "(no answer)"

        # Record the turn for downstream Flink intent analysis. Best-effort: the
        # producer never raises, so a Kafka hiccup can't break the reply.
        from chat import conversation_producer

        conversation_producer.produce_turn(
            session_id, message, answer,
            model=config.settings.LLM_MODEL, source_mode="live",
        )
        return ChatResponse(reply=answer, source_mode="live", session_id=session_id)
    except Exception:
        logger.exception("chat agent failed")
        return ChatResponse(
            reply="Sorry — I couldn't reach the assistant backend just now. Please try again.",
            source_mode="error",
            session_id=session_id,
        )


async def reset_session(session_id: str) -> bool:
    """Close and forget a cached session. Returns whether one existed."""
    try:
        from chat import agent

        return await agent.reset_session(session_id)
    except Exception:
        logger.exception("chat session reset failed")
        return False
