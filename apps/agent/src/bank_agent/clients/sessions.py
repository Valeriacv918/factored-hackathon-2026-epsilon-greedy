"""Session lookup for Services.validate_session: session_ref -> trusted customer_id.

StaticSessions is for development only: it maps fixed references to real
customers so the graph can run against real data without the login agent.
An IdentityValidator-backed resolver replaces it once the validator's
customer_id normalization keeps hyphens (real IDs look like CLI-XXXX).
"""
from typing import Protocol


class SessionResolver(Protocol):
    def resolve(self, session_ref: str) -> str | None:
        """Return the authenticated customer_id, or None if the session is not valid."""
        ...


class StaticSessions:
    def __init__(self, mapping: dict[str, str]):
        self._mapping = dict(mapping)

    @classmethod
    def from_string(cls, spec: str) -> "StaticSessions":
        """Parse 'ref=CUSTOMER_ID,ref2=CUSTOMER_ID2' (the DEV_SESSIONS format)."""
        mapping = {}
        for item in filter(None, (part.strip() for part in spec.split(","))):
            ref, sep, customer = (x.strip() for x in item.partition("="))
            if not sep or not ref or not customer:
                raise ValueError(f"Invalid session entry {item!r}; expected ref=CUSTOMER_ID.")
            mapping[ref] = customer
        return cls(mapping)

    def resolve(self, session_ref: str) -> str | None:
        return self._mapping.get(session_ref)
