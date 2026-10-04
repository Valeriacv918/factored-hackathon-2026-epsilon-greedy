"""Session lookup for Services: session_ref -> SessionGrant(customer_id, session token).

The token is signed by the MCP server (verify_identity) and is what the server
trusts on every call; customer_id here is only for the graph's own checks. Tokens
stay in this resolver, outside the LangGraph checkpoint (graphs/state.py).

- ValidatorSessions: production. session_ref is the IdentityValidator session id.
- StaticSessions: development only. DEV_SESSIONS maps fixed refs to tokens minted
  with `uv run --project apps/mcp-server bank-mcp-token CUSTOMER_ID`.
"""
import base64
import binascii
import json
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SessionGrant:
    customer_id: str
    token: str

    def __repr__(self) -> str:   # keep the bearer token out of logs and tracebacks
        return f"SessionGrant(customer_id={self.customer_id!r}, token=<redacted>)"


class SessionResolver(Protocol):
    def resolve(self, session_ref: str) -> SessionGrant | None:
        """Return the authenticated grant, or None if the session is not valid."""
        ...


def token_customer(token: str) -> str:
    """Read customer_id from a token WITHOUT checking the signature.

    Only for local bookkeeping: the server verifies the signature on every call,
    so a forged token gets nothing from it.
    """
    try:
        payload = token.split(".")[0]
        customer = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["sub"]
    except (ValueError, KeyError, TypeError, IndexError, binascii.Error):
        raise ValueError("Not a session token; mint one with bank-mcp-token.") from None
    if not isinstance(customer, str) or not customer:
        raise ValueError("Not a session token; mint one with bank-mcp-token.")
    return customer


class StaticSessions:
    def __init__(self, tokens: dict[str, str]):
        self._grants = {ref: SessionGrant(token_customer(token), token) for ref, token in tokens.items()}

    @classmethod
    def from_string(cls, spec: str) -> "StaticSessions":
        """Parse 'ref=TOKEN,ref2=TOKEN2' (the DEV_SESSIONS format)."""
        mapping = {}
        for item in filter(None, (part.strip() for part in spec.split(","))):
            ref, sep, token = (x.strip() for x in item.partition("="))
            if not sep or not ref or not token:
                raise ValueError(f"Invalid DEV_SESSIONS entry for {ref or '?'!r}; expected ref=TOKEN.")
            mapping[ref] = token
        return cls(mapping)

    def resolve(self, session_ref: str) -> SessionGrant | None:
        return self._grants.get(session_ref)


class ValidatorSessions:
    """Sessions authenticated by IdentityValidator; expiry follows its TTL."""

    def __init__(self, validator):
        self._validator = validator   # nodes.validator_agent.validator.IdentityValidator

    def resolve(self, session_ref: str) -> SessionGrant | None:
        if not self._validator.is_authenticated(session_ref):
            return None
        session = self._validator.get_session(session_ref)
        if not session.customer_id or not session.session_token:
            return None
        return SessionGrant(session.customer_id, session.session_token)
