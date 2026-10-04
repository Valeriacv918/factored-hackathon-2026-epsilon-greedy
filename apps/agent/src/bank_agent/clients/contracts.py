from datetime import datetime
from typing import Any, Protocol


class ServiceFailure(Exception):
    """Timeout, malformed response, or unverified result; safe to route to fallback."""


class SessionExpired(Exception):
    """The current session no longer authorizes this conversation."""


class Services(Protocol):
    """Adapter boundary. Real MCP and model adapters are intentionally not supplied.

    Every tool must validate the session and enforce ownership server-side. Mutations
    must atomically deduplicate by idempotency_key and return the original receipt
    on retries. read_* must independently read persisted state. Monetary values are
    decimal strings, timestamps timezone-aware. See clients/README.md for schemas.
    """

    def now(self) -> datetime: ...
    def detect_language(self, text: str) -> str | None: ...
    def validate_session(self, session_ref: str) -> str | None:
        """Return trusted customer ID, or None. Never infer identity from the message."""
        ...
    def understand(self, text: str, language: str) -> dict[str, Any]: ...
    def tool(self, name: str, *, session_ref: str, customer_id: str,
             arguments: dict[str, Any]) -> dict[str, Any]: ...
