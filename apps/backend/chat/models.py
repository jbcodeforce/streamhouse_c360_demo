"""Pydantic models for the Assistant chat.

The Assistant is a natural-language chat over the C360 data. The welcome prompt
comes from config (``CHAT_FIRST_PROMPT``). ``ChatRequest.history`` carries prior
turns so the local agent has conversation context when it queries
``fct_c360_profile`` via RTCE.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """One turn in the conversation."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """A user question plus the prior turns of the conversation.

    ``session_id`` is a UUID the chat UI mints on the first submit and keeps for
    the whole conversation. The backend uses it to reuse one cached MCP/agent
    connection across the session's turns; omit it for a stateless one-off.
    """

    message: str
    history: list[ChatMessage] = []
    session_id: str | None = None


class ChatResponse(BaseModel):
    """The assistant's reply.

    ``source_mode`` is "live" (agent answered) or "error".
    ``session_id`` echoes the request's session so the UI can display it.
    """

    reply: str
    source_mode: str = "live"
    session_id: str | None = None


class ResetRequest(BaseModel):
    """Close and forget a cached chat session (the UI's "reset" action)."""

    session_id: str


class WelcomeResponse(BaseModel):
    """The greeting shown in the chat's empty state, from ``CHAT_FIRST_PROMPT``."""

    prompt: str
    source_mode: str = "live"
