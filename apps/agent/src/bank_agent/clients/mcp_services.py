"""Services implementation over the bank MCP server (read tools only for now).

- The server learns the customer from the session token, never from an argument;
  the token comes from the resolved session, never from model output.
- Only allow-listed arguments reach the server.
- Tools the server does not offer yet (writes, dispute_context) raise
  ServiceFailure, which the graph turns into an escalation or a safe
  "service unavailable" ending, never a claimed success.
"""
import datetime as dt
import os
import shlex
from pathlib import Path
from typing import Any, Callable, Mapping

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.clients.mcp_client import McpToolClient
from bank_agent.clients.sessions import SessionResolver, StaticSessions
from bank_agent.clients.understanding import LlmUnderstanding
from bank_agent.clients.narrative import LlmNarrator

REPO_ROOT = Path(__file__).resolve().parents[5]

# Tool name -> arguments the graph may pass through. session_token is added here.
READ_TOOLS = {
    "find_transactions": ("slots", "limit", "window_days"),
    "list_cards": (),
    "get_card": ("card_id",),
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def scenario_clock(start: dt.datetime) -> Callable[[], dt.datetime]:
    """Time runs forward from `start`, so the policy window matches historical data."""
    if start.tzinfo is None:
        raise ValueError("SCENARIO_NOW must include a timezone, e.g. 2026-06-18T12:00:00+00:00.")
    offset = start - utc_now()
    return lambda: utc_now() + offset


def detect_language_lingua(text: str) -> str | None:
    from bank_agent.nodes.validator_agent.language import detect_language
    result = detect_language(text)
    return None if result.ambiguous else result.language


def mcp_client_from_env(env: Mapping[str, str] = os.environ) -> McpToolClient:
    """MCP_SERVER_URL (streamable HTTP) if set, else MCP_SERVER_COMMAND over stdio."""
    if env.get("MCP_SERVER_URL"):
        return McpToolClient(url=env["MCP_SERVER_URL"])
    command, *args = shlex.split(env.get("MCP_SERVER_COMMAND") or "uv run --project apps/mcp-server bank-mcp")
    if not Path(command).is_absolute() and (REPO_ROOT / command).exists():
        command = str(REPO_ROOT / command)
    return McpToolClient(command=command, args=args, cwd=REPO_ROOT)


class McpServices:
    def __init__(self, client, sessions: SessionResolver, understanding, *,
                clock: Callable[[], dt.datetime] = utc_now,
                language_detector: Callable[[str], str | None] = detect_language_lingua,
                narrator: LlmNarrator | None = None):
        self._client, self._sessions, self._understanding = client, sessions, understanding
        self._clock, self._detect, self._narrator = clock, language_detector, narrator

    @classmethod

    def from_env(cls, env: Mapping[str, str] = os.environ) -> "McpServices":
        from bank_agent.config.settings import settings
        clock = scenario_clock(dt.datetime.fromisoformat(env["SCENARIO_NOW"])) if env.get("SCENARIO_NOW") else utc_now
        client = mcp_client_from_env(env)
        model_id = env.get("LLM_MODEL") or settings.llm_model
        understanding = LlmUnderstanding.from_model_id(model_id, clock)
        return cls(client, StaticSessions.from_string(env.get("DEV_SESSIONS", "")), understanding, clock=clock,
                   narrator=LlmNarrator.from_model_id(model_id))

    def close(self) -> None:
        self._client.close()

    def now(self) -> dt.datetime:
        return self._clock()

    def detect_language(self, text: str) -> str | None:
        return self._detect(text)

    def validate_session(self, session_ref: str) -> str | None:
        grant = self._sessions.resolve(session_ref)
        return grant.customer_id if grant else None

    def understand(self, text: str, language: str) -> dict[str, Any]:
        return self._understanding.understand(text, language)

    def write_narrative(self, facts: dict[str, Any], language: str) -> str:
        if self._narrator is None:
            raise ServiceFailure("No narrative model configured")
        return self._narrator.write(facts, language)

    def tool(self, name: str, *, session_ref: str, customer_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        grant = self._sessions.resolve(session_ref)
        if not customer_id or grant is None or grant.customer_id != customer_id:
            raise SessionExpired()
        if name not in READ_TOOLS:
            raise ServiceFailure(f"{name} is not available yet")
        mcp_arguments = {key: arguments[key] for key in READ_TOOLS[name] if key in arguments}
        mcp_arguments["session_token"] = grant.token
        if name == "find_transactions":
            mcp_arguments["reference_date"] = self.now().date().isoformat()
        return self._client.call(name, mcp_arguments)
