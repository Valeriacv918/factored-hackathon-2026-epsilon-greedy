"""Identity check for the validator: customer_id + date of birth + product number.

The agent never reads customer records. The MCP server compares the values in SQL
and answers only verified / failed / locked, plus a signed session token and the
customer's product numbers on success. The date of birth never leaves the server.

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
    def verify(self, customer_id: str, date_of_birth: date, product_number: str) -> IdentityResult:
        """Raise ServiceFailure if the check could not be made (outage, timeout)."""
        ...


class McpIdentityChecker:
    def __init__(self, client):
        self._client = client   # McpToolClient

    def verify(self, customer_id: str, date_of_birth: date, product_number: str) -> IdentityResult:
        result = self._client.call("verify_identity", {"customer_id": customer_id,
                                                       "date_of_birth": date_of_birth.isoformat(),
                                                       "product_number": product_number})
        try:
            status = result.get("status")
            if status == "verified":
                if not result.get("session_token"):
                    raise ServiceFailure("verify_identity returned no session token")
                return IdentityResult("verified", customer_id, tuple(result.get("product_numbers") or ()),
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

    Behaves like the server's verify_identity: counts failures per customer_id
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

    def verify(self, customer_id: str, date_of_birth: date, product_number: str) -> IdentityResult:
        self.calls += 1
        if self.fail:
            raise ServiceFailure("simulated outage")
        now = self.clock()
        until = self._locked_until.get(customer_id)
        if until and now < until:
            return IdentityResult("locked", locked_until=until)
        record = self.records.get(customer_id)
        numbers = tuple(p.product_number.upper() for p in record.products) if record else ()
        if record is None or record.date_of_birth != date_of_birth or product_number.upper() not in numbers:
            self._failures[customer_id] = self._failures.get(customer_id, 0) + 1
            left = self.max_attempts - self._failures[customer_id]
            if left > 0:
                return IdentityResult("failed", attempts_left=left)
            del self._failures[customer_id]
            self._locked_until[customer_id] = now + self.lockout
            return IdentityResult("locked", locked_until=now + self.lockout)
        self._failures.pop(customer_id, None)
        self._locked_until.pop(customer_id, None)
        return IdentityResult("verified", record.customer_id, numbers, f"test-token:{record.customer_id}",
                              expires_at=now + self.ttl)
