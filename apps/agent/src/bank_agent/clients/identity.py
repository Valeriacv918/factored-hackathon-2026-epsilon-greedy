"""Identity check for the validator: customer_id + date of birth + product number.

The agent never reads customer records. The MCP server compares the values in SQL
and answers only verified / failed / locked, plus a signed session token and the
customer's product numbers on success. The date of birth never leaves the server.

- McpIdentityChecker: production, calls the server's `verify_identity` tool.
- InMemoryIdentityChecker: SYNTHETIC data for tests and demos, same answers.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional, Protocol

from bank_agent.clients.contracts import ServiceFailure

IdentityStatus = Literal["verified", "failed", "locked"]


@dataclass(frozen=True)
class IdentityResult:
    status: IdentityStatus
    customer_id: Optional[str] = None
    product_numbers: tuple = ()               # tuple[str, ...], normalized (upper, no spaces/dashes)
    session_token: Optional[str] = None


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
        status = result.get("status")
        if status == "verified":
            if not result.get("session_token"):
                raise ServiceFailure("verify_identity returned no session token")
            return IdentityResult("verified", customer_id, tuple(result.get("product_numbers") or ()),
                                  result["session_token"])
        if status in ("failed", "locked"):
            return IdentityResult(status)
        raise ServiceFailure("verify_identity returned an unknown status")


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


class InMemoryIdentityChecker:
    """SYNTHETIC data only. Never put real customers here."""

    def __init__(self, records: dict[str, CustomerRecord], fail: bool = False):
        self.records = records
        self.fail = fail
        self.calls = 0

    def verify(self, customer_id: str, date_of_birth: date, product_number: str) -> IdentityResult:
        self.calls += 1
        if self.fail:
            raise ServiceFailure("simulated outage")
        record = self.records.get(customer_id)
        numbers = tuple(p.product_number.upper() for p in record.products) if record else ()
        if record is None or record.date_of_birth != date_of_birth or product_number.upper() not in numbers:
            return IdentityResult("failed")
        return IdentityResult("verified", record.customer_id, numbers, f"test-token:{record.customer_id}")
