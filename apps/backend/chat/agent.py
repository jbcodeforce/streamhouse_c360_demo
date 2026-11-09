"""agno agent for the Assistant chat (live mode).

Wires a local OpenAI-compatible LLM (an MLX server) to the Confluent Real-Time
Context Engine context-engine MCP server. The agent answers customer questions
by discovering the topic schema and running SQL point queries over
``fct_c360_profile``.

Two execution modes:

* **sessioned** — when a ``session_id`` is given (the chat UI mints a UUID on the
  first submit), the MCP connection + agent are opened once and cached, then
  reused for every later turn of that session until it is reset or evicted. This
  avoids re-doing the MCP handshake on each message.
* **stateless** — no ``session_id``: a fresh connection per request.

Both inject the frontend-supplied ``history`` into the prompt, so conversation
continuity does not depend on agno's internal memory.

Kept separate from ``chat.service`` so unconfigured mode never imports agno, and
so tests can monkeypatch the connector without any LLM/MCP infrastructure. The heavy
agno imports are deferred into the connect helpers for the same reason.

The MCP server URL is derived from the Confluent coordinates
(``config.settings.rtce_mcp_url()``) so it can't drift out of sync. Auth is HTTP
Basic with the org-wide GLOBAL key. Static headers must ride on
``StreamableHTTPClientParams`` (server_params) so they apply during the initial
handshake — the plain ``headers=`` arg on ``MCPTools`` is not reliably applied to
a secured server (agno#9442).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time

import config
from chat.models import ChatMessage

logger = logging.getLogger("c360.chat")

PROFILE_TABLE = "fct_c360_profile"
_MCP_TIMEOUT_SECONDS = 30
_HISTORY_TURNS = 8
_MAX_ROWS = 20
# The RTCE context-engine MCP server (early access) can return a transient error
# during the initialize handshake, and a cached connection can drop. The queries
# are read-only (SELECT), so retrying — and reconnecting a session — is safe.
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.75
# Cached-session bounds, to keep open MCP connections from accumulating.
_MAX_SESSIONS = 20
_SESSION_TTL_SECONDS = 1800  # 30 minutes idle

_INSTRUCTIONS = [
    "You are the C360 Assistant for the customer-360 demo.",
    "Answer questions about customers, their accounts, and their transactions"
    f" using the '{PROFILE_TABLE}' topic (one row per customer) via the MCP tools.",
    "Follow this order every time:",
    f"1) Call getMetadata(topic_name='{PROFILE_TABLE}') to learn the exact column"
    " names and types. Never guess column names.",
    f"2) Call queryData(topic_name='{PROFILE_TABLE}', query=<SQL SELECT>,"
    f" max_result_rows={_MAX_ROWS}). Double-quote every column name using the"
    " exact casing from getMetadata (e.g. WHERE \"last_name\" = 'Carter').",
    "For a person's name, match on the name column(s) you find (e.g. last_name)."
    " Use customer_id when the user gives one.",
    "Be concise. Report the fields you found. If the query returns no rows, say so"
    " plainly rather than guessing.",
]


# --------------------------------------------------------------------------- #
# Prompt / auth / diagnostics helpers
# --------------------------------------------------------------------------- #

def _basic_auth_header() -> str:
    """``Authorization: Basic …`` for the GLOBAL key, as the MCP server expects."""
    key = config.settings.CONFLUENT_GLOBAL_KEY or ""
    secret = config.settings.CONFLUENT_GLOBAL_SECRET or ""
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    return f"Basic {token}"


def _target_summary() -> str:
    """Masked description of what we connect to, for diagnosing env/cred drift.

    A -32603/401 from the server almost always means a wrong URL or a stale
    GLOBAL key captured at process start — this line lets a failing process name
    its own target so it can be compared against a known-good one.
    """
    s = config.settings
    key = s.CONFLUENT_GLOBAL_KEY or ""
    masked = f"{key[:4]}..{key[-2:]}({len(key)})" if key else "EMPTY"
    secret_len = len(s.CONFLUENT_GLOBAL_SECRET or "")
    return f"url={s.rtce_mcp_url()} key={masked} secret_len={secret_len}"


def _error_detail(exc: Exception) -> str:
    """Pull the MCP/JSON-RPC specifics (code/message/data) out of an error."""
    bits = [type(exc).__name__]
    for attr in ("code", "message", "data"):
        value = getattr(exc, attr, None)
        if value is not None:
            bits.append(f"{attr}={value}")
    text = str(exc)
    if text and text not in bits:
        bits.append(f"str={text}")
    return " ".join(bits)


def _history_text(history: list[ChatMessage]) -> str:
    """Render the most recent turns as plain context for the prompt."""
    return "\n".join(f"{m.role}: {m.content}" for m in history[-_HISTORY_TURNS:])


def _build_prompt(message: str, history: list[ChatMessage]) -> str:
    ctx = _history_text(history)
    return f"Conversation so far:\n{ctx}\n\nUser: {message}" if ctx else message


# --------------------------------------------------------------------------- #
# agno construction (the live pieces — monkeypatched in tests)
# --------------------------------------------------------------------------- #

def _build_model_and_params():
    """Build the OpenAILike model and the MCP StreamableHTTPClientParams."""
    from agno.models.openai.like import OpenAILike
    from agno.tools.mcp import StreamableHTTPClientParams

    s = config.settings
    model = OpenAILike(
        id=s.LLM_MODEL,
        base_url=s.LLM_BASE_URL,
        api_key=s.LLM_API_KEY,
        temperature=s.LLM_TEMPERATURE,
    )
    server_params = StreamableHTTPClientParams(
        url=s.rtce_mcp_url(),
        headers={"Authorization": _basic_auth_header()},
    )
    return model, server_params


async def _run_stateless(prompt: str) -> str:
    """One self-contained attempt: open an MCP session, run, close it."""
    from agno.agent import Agent
    from agno.tools.mcp import MCPTools

    model, server_params = _build_model_and_params()
    async with MCPTools(
        server_params=server_params,
        transport="streamable-http",
        timeout_seconds=_MCP_TIMEOUT_SECONDS,
    ) as tools:
        agent = Agent(model=model, tools=[tools], instructions=_INSTRUCTIONS, markdown=False)
        result = await agent.arun(input=prompt)
    return (result.content or "").strip()


async def _connect(session_id: str):
    """Open a PERSISTENT MCP connection and build a reusable agent.

    Returns ``(agent, tools)``; the caller owns closing ``tools`` later.
    """
    from agno.agent import Agent
    from agno.tools.mcp import MCPTools

    model, server_params = _build_model_and_params()
    tools = MCPTools(
        server_params=server_params,
        transport="streamable-http",
        timeout_seconds=_MCP_TIMEOUT_SECONDS,
    )
    await tools.connect()
    agent = Agent(
        model=model,
        tools=[tools],
        instructions=_INSTRUCTIONS,
        markdown=False,
        session_id=session_id,
    )
    return agent, tools


# --------------------------------------------------------------------------- #
# Session cache
# --------------------------------------------------------------------------- #

class _CachedSession:
    __slots__ = ("agent", "tools", "lock", "last_used")

    def __init__(self, agent, tools) -> None:
        self.agent = agent
        self.tools = tools
        self.lock = asyncio.Lock()  # serialize turns within this session
        self.last_used = time.monotonic()


# session_id -> _CachedSession. Mutated only from the event loop thread; the
# awaits that could interleave are guarded by double-checking after them.
_sessions: dict[str, _CachedSession] = {}


async def _close(entry: _CachedSession) -> None:
    try:
        await entry.tools.close()
    except Exception:  # noqa: BLE001 — best-effort cleanup
        logger.debug("error closing MCP session", exc_info=True)


def _collect_evictable() -> list[_CachedSession]:
    """Pop idle-expired and over-cap (LRU) sessions; return them to close."""
    now = time.monotonic()
    victims: list[_CachedSession] = []
    for sid in [s for s, e in _sessions.items() if now - e.last_used > _SESSION_TTL_SECONDS]:
        victims.append(_sessions.pop(sid))
    while len(_sessions) > _MAX_SESSIONS:
        lru = min(_sessions, key=lambda k: _sessions[k].last_used)
        victims.append(_sessions.pop(lru))
    return victims


async def _get_or_create(session_id: str) -> _CachedSession:
    for victim in _collect_evictable():
        await _close(victim)

    entry = _sessions.get(session_id)
    if entry is None:
        agent, tools = await _connect(session_id)
        # Another turn for the same new session could have connected during the
        # await above — keep the first, close the loser.
        existing = _sessions.get(session_id)
        if existing is not None:
            await _close(_CachedSession(agent, tools))
            entry = existing
        else:
            entry = _CachedSession(agent, tools)
            _sessions[session_id] = entry
    entry.last_used = time.monotonic()
    return entry


async def _evict(session_id: str) -> bool:
    entry = _sessions.pop(session_id, None)
    if entry is None:
        return False
    await _close(entry)
    return True


async def reset_session(session_id: str) -> bool:
    """Close and forget a cached session. Returns whether one existed."""
    return await _evict(session_id)


async def shutdown() -> None:
    """Close every cached session (call from the app lifespan)."""
    entries = list(_sessions.values())
    _sessions.clear()
    for entry in entries:
        await _close(entry)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

async def run_agent(
    message: str,
    history: list[ChatMessage],
    session_id: str | None = None,
) -> str:
    """Run one turn and return the text answer.

    With a ``session_id`` the MCP connection + agent are cached and reused; a
    failed turn drops the (possibly broken) connection and the next attempt
    reconnects. Without one, each call is a fresh stateless connection.
    """
    prompt = _build_prompt(message, history)

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            if session_id:
                entry = await _get_or_create(session_id)
                async with entry.lock:
                    result = await entry.agent.arun(input=prompt, session_id=session_id)
                return (result.content or "").strip()
            return await _run_stateless(prompt)
        except Exception as exc:  # noqa: BLE001 — retry/reconnect any failure
            last_exc = exc
            logger.warning(
                "RTCE MCP agent attempt %d/%d failed (session=%s): %s | target %s",
                attempt, _MAX_ATTEMPTS, session_id or "-", _error_detail(exc), _target_summary(),
            )
            if session_id:
                await _evict(session_id)  # drop a possibly-broken cached connection
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)

    assert last_exc is not None
    raise last_exc
