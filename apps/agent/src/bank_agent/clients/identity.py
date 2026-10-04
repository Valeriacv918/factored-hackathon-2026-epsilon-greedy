"""Identity check for the validator: document_number + date of birth + product number.

The customer identifies with the document they know (cédula, CURP, DNI...). The agent
never reads customer records. The MCP server compares the values in SQL and answers
only verified / failed / locked, plus, on success, the customer's internal customer_id
(for traceability), a signed session token and their product numbers. The date of
birth never leaves the server.

The server also owns the limits (attempts, lockout, session lifetime) and reports
them in each answer, so the agent never keeps its own copy of those numbers.
Times are real UTC: compare them with a real clock, never the scenario clock.

- McpIdentityChecker: production, calls the server's `verify_identity` tool.
- InMemoryIdentityChecker: SYNTHETIC data for tests and demos, same answers.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Literal, Optional, Protocol

from bank_agent.clients.contracts import ServiceFailure

IdentityStatus = Literal["verified", "failed", "locked"]


@dataclass(frozen=True)
class IdentityResult:
    status: IdentityStatus
    customer_id: Optional[str] = None
    product_numbers: tuple = ()               # tuple[str, ...], normalized (upper, no spaces/dashes)
    session_token: Optional[str] = None
    attempts_left: Optional[int] = None       # on "failed"
    locked_until: Optional[datetime] = None   # on "locked"
    expires_at: Optional[datetime] = None     # on "verified": when the session token expires


class IdentityChecker(Protocol):
    def verify(self, document_number: str, date_of_birth: date, product_number: str) -> IdentityResult:
        """Raise ServiceFailure if the check could not be made (outage, timeout)."""
        ...


class McpIdentityChecker:
    def __init__(self, client):
        self._client = client   # McpToolClient

    def verify(self, document_number: str, date_of_birth: date, product_number: str) -> IdentityResult:
        result = self._client.call("verify_identity", {"document_number": document_number,
                                                       "date_of_birth": date_of_birth.isoformat(),
                                                       "product_number": product_number})
        try:
            status = result.get("status")
            if status == "verified":
                if not result.get("session_token") or not result.get("customer_id"):
                    raise ServiceFailure("verify_identity returned no session token or customer_id")
                return IdentityResult("verified", result["customer_id"], tuple(result.get("product_numbers") or ()),
                                      result["session_token"], expires_at=_utc(result["expires_at"]))
            if status == "failed":
                return IdentityResult("failed", attempts_left=int(result["attempts_left"]))
            if status == "locked":
                return IdentityResult("locked", locked_until=_utc(result["locked_until"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceFailure("verify_identity returned an invalid result") from exc
        raise ServiceFailure("verify_identity returned an unknown status")


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp without timezone")
    return parsed


# ---------- In memory (tests / demo) ----------

@dataclass(frozen=True)
class Product:
    product_number: str
    product_type: Optional[str] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class CustomerRecord:
    customer_id: str
    date_of_birth: Optional[date]
    products: tuple = field(default_factory=tuple)   # tuple[Product, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryIdentityChecker:
    """SYNTHETIC data only. Never put real customers here.

    `records` is keyed by document_number; each record carries the internal customer_id.
    Behaves like the server's verify_identity: counts failures per document
    (any string, known or not), locks after `max_attempts`, and issues sessions
    that expire after `ttl`. These defaults belong to this fake, not to the agent.
    """

    def __init__(self, records: dict[str, CustomerRecord], fail: bool = False, *,
                 clock: Callable[[], datetime] = _utc_now, max_attempts: int = 3,
                 lockout: timedelta = timedelta(minutes=15), ttl: timedelta = timedelta(minutes=15)):
        self.records = records
        self.fail = fail
        self.calls = 0
        self.clock, self.max_attempts, self.lockout, self.ttl = clock, max_attempts, lockout, ttl
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, datetime] = {}

    def verify(self, document_number: str, date_of_birth: date, product_number: str) -> IdentityResult:
        self.calls += 1
        if self.fail:
            raise ServiceFailure("simulated outage")
        now = self.clock()
        until = self._locked_until.get(document_number)
        if until and now < until:
            return IdentityResult("locked", locked_until=until)
        record = self.records.get(document_number)
        numbers = tuple(p.product_number.upper() for p in record.products) if record else ()
        if record is None or record.date_of_birth != date_of_birth or product_number.upper() not in numbers:
            self._failures[document_number] = self._failures.get(document_number, 0) + 1
            left = self.max_attempts - self._failures[document_number]
            if left > 0:
                return IdentityResult("failed", attempts_left=left)
            del self._failures[document_number]
            self._locked_until[document_number] = now + self.lockout
            return IdentityResult("locked", locked_until=now + self.lockout)
        self._failures.pop(document_number, None)
        self._locked_until.pop(document_number, None)
        return IdentityResult("verified", record.customer_id, numbers, f"test-token:{record.customer_id}",
                              expires_at=now + self.ttl)
