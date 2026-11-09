"""FastAPI router for the /chat endpoints (Assistant).

``GET /chat/welcome`` returns the initial greeting; ``POST /chat`` runs the
agno agent against the local LLM + RTCE context-engine MCP server.
See ``chat.service``.
"""

from __future__ import annotations

from fastapi import APIRouter

from chat import service
from chat.models import ChatRequest, ChatResponse, ResetRequest, WelcomeResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/welcome", response_model=WelcomeResponse, status_code=200)
def get_welcome() -> WelcomeResponse:
    """The empty-state greeting, sourced from ``CHAT_FIRST_PROMPT``."""
    return service.get_welcome()


@router.post("", response_model=ChatResponse, status_code=200)
async def post_chat(request: ChatRequest) -> ChatResponse:
    """Answer a user question.

    Runs the agno agent against the local LLM + RTCE context-engine MCP server,
    reusing the session's cached connection when a ``session_id`` is supplied.
    Always 200 — failures or unconfigured state come back as a reply with
    ``source_mode="error"``.
    """
    return await service.get_reply(request)


@router.post("/reset", status_code=200)
async def reset_chat(request: ResetRequest) -> dict:
    """Close and forget a cached session (the UI's reset action)."""
    cleared = await service.reset_session(request.session_id)
    return {"cleared": cleared}
