"""Services implementation over the bank MCP server.

- The server learns the customer from the session token, never from an argument;
  the token comes from the resolved session, never from model output.
- Only allow-listed tools and arguments reach the server.
- Card blocks, disputes, handoffs and notifications are SIMULATED writes in the
  server's sandbox scenario (docs/mcp-sandbox.md); the graph proves each one with
  its read_* tool.
- Tools the server does not offer (account suspension) raise ServiceFailure, which the graph turns into an escalation or a safe
  "service unavailable" ending, never a claimed success. list_accounts/get_account
  are allowed through but the server has no such tools yet, so they fail the same way.
"""
import datetime as dt
import os
import shlex
from pathlib import Path
from typing import Any, Callable, Mapping

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.clients.mcp_client import McpToolClient
from bank_agent.clients.sessions import SessionResolver, StaticSessions, ValidatorSessions
from bank_agent.clients.understanding import LlmUnderstanding
from bank_agent.clients.narrative import LlmNarrator

REPO_ROOT = Path(__file__).resolve().parents[5]

# Tool name -> arguments the graph may pass through. session_token is added here.
TOOLS = {
    "save_charge_explanation": ("conversation_id", "transaction_id", "observed_status"),
    "find_transactions": ("slots", "limit", "window_days"),
    "list_cards": (),
    "get_card": ("card_id",),
    "list_accounts": (),
    "get_account": ("account_id",),
    "dispute_context": ("transaction_id",),
    "block_card": ("card_id", "idempotency_key"),
    "read_block": ("id",),
    "file_dispute": ("transaction_id", "idempotency_key"),
    "read_dispute": ("id",),
    "create_handoff": ("packet", "idempotency_key"),
    "read_handoff": ("id",),
    "notify_employee": ("ticket_id", "idempotency_key"),
    "read_notification": ("id",),
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
        self._validation_agents = {}
        self._identity_sessions = {}
        self._identity_validator = None
        self._triage_classifier = None

    @classmethod

    def from_env(cls, env: Mapping[str, str] = os.environ) -> "McpServices":
        from bank_agent.config.settings import settings
        clock = scenario_clock(dt.datetime.fromisoformat(env["SCENARIO_NOW"])) if env.get("SCENARIO_NOW") else utc_now
        client = mcp_client_from_env(env)
        model_id = env.get("LLM_MODEL") or settings.llm_model
        understanding = LlmUnderstanding.from_model_id(model_id, clock)
        return cls(client, StaticSessions.from_string(env.get("DEV_SESSIONS", "")), understanding, clock=clock,
                   narrator=LlmNarrator.from_model_id(model_id))

    def _validator(self):
        from bank_agent.clients.identity import McpIdentityChecker
        from bank_agent.nodes.validator_agent.validator import IdentityValidator
        if self._identity_validator is None:
            # Real time for authentication TTL; historical clock is for transaction searches.
            self._identity_validator = IdentityValidator(McpIdentityChecker(self._client))
        return self._identity_validator

    def validation_agent(self, conversation_id):
        from bank_agent.nodes.validator_agent.agent import ValidationAgent
        if conversation_id not in self._validation_agents:
            self._validation_agents[conversation_id] = ValidationAgent(self._validator())
        return self._validation_agents[conversation_id]

    def verify_identity(self, conversation_id: str, document_number: str, date_of_birth: str,
                        product_number: str) -> dict[str, Any]:
        """Verify form factors through MCP and return only status plus an opaque session reference."""
        validator = self._validator()
        if conversation_id not in self._identity_sessions:
            self._identity_sessions[conversation_id] = validator.new_session().session_id
        session_ref = self._identity_sessions[conversation_id]
        result = validator.verify(session_ref, document_number, date_of_birth, product_number)
        return {"status": result.status.value, "attempts_left": result.attempts_left,
                "missing_fields": list(result.missing_fields), "session_ref": session_ref}

    def triage_understand(self, text):
        from bank_agent.nodes.triage_agent.classifier import LLMClassifier
        if self._triage_classifier is None:
            self._triage_classifier = LLMClassifier()
        return self._triage_classifier.understand(text)

    def close(self) -> None:
        self._validation_agents.clear()
        self._identity_sessions.clear()
        self._client.close()

    def now(self) -> dt.datetime:
        return self._clock()

    def detect_language(self, text: str) -> str | None:
        return self._detect(text)

    def _session_grant(self, session_ref):
        if self._identity_validator is not None:
            if session_ref in self._identity_validator._sessions:
                return ValidatorSessions(self._identity_validator).resolve(session_ref)
        return self._sessions.resolve(session_ref)

    def validate_session(self, session_ref: str) -> str | None:
        grant = self._session_grant(session_ref)
        return grant.customer_id if grant else None

    def understand(self, text: str, language: str) -> dict[str, Any]:
        return self._understanding.understand(text, language)

    def write_narrative(self, facts: dict[str, Any], language: str) -> str:
        if self._narrator is None:
            raise ServiceFailure("No narrative model configured")
        return self._narrator.write(facts, language)

    def tool(self, name: str, *, session_ref: str, customer_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        grant = self._session_grant(session_ref)
        if not grant or not customer_id or grant.customer_id != customer_id:
            raise SessionExpired()
        if name not in TOOLS:
            raise ServiceFailure(f"{name} is not available yet")
        mcp_arguments = {key: arguments[key] for key in TOOLS[name] if key in arguments}
        mcp_arguments["session_token"] = grant.token
        if name == "find_transactions":
            mcp_arguments["reference_date"] = self.now().date().isoformat()
        return self._client.call(name, mcp_arguments)
