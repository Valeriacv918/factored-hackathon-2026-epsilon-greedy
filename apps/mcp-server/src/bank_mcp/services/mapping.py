"""bank_curated rows -> the record shapes the agent expects (apps/agent clients/README.md).

This is the single place where table column names are translated:
transaction_id -> id, transaction_status -> status, transaction_date -> date,
product_id (when the product is a card) -> card_id, product_status -> status.
Amounts are decimal strings, never floats; timestamps are ISO 8601 with zone.
Missing values stay null: the agent's policy escalates instead of imputing.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bank_mcp.sql.queries import CARD_TYPES


class Transaction(BaseModel):
    id: str
    customer_id: str
    card_id: str | None
    status: str
    fraud_score: str | None
    amount: str
    amount_usd: str | None
    amount_usd_original: str | None = None
    amount_usd_source: str | None = None
    fx_rate: str | None = None
    fx_date: str | None = None
    fx_run_id: str | None = None
    currency: str
    date: str
    local_date: str | None = None
    customer_timezone: str | None = None
    merchant: str | None


class TransactionSearch(BaseModel):
    transactions: list[Transaction]
    has_more: bool


class Card(BaseModel):
    id: str
    customer_id: str
    last4: str | None
    status: str
    type: str


class CardList(BaseModel):
    cards: list[Card]


class ActionReceipt(BaseModel):
    """What a write returns: only the id. The agent proves the effect with read_*."""
    id: str


class BlockRecord(BaseModel):
    id: str
    card_id: str
    customer_id: str
    status: str
    verified: bool


class DisputeRecord(BaseModel):
    id: str
    customer_id: str
    transaction_id: str
    status: str
    verified: bool


class DisputeContext(BaseModel):
    existing_case_id: str | None   # an OPEN dispute on this transaction in this scenario
    recent_dispute_count: int      # curated complaints only, see docs/mcp-sandbox.md


Code = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
ItemId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Issue = Annotated[str, Field(min_length=1, max_length=120)]


class HandoffPacket(BaseModel):
    """What a human agent needs to pick up the case (escalation node in apps/agent).

    The server stores only these fields, so no token or other extra data reaches the
    table. Every id listed must belong to the session's customer (checked in SQL).
    """
    model_config = ConfigDict(extra="forbid")

    reason: Code
    queue: Code
    priority: Literal["P1", "P2", "P3"]
    language: Literal["es", "pt"]
    customer_quote: str = Field(max_length=1000)
    transaction_ids: list[ItemId] = Field(max_length=20)
    case_ids: list[ItemId] = Field(max_length=20)
    blocked_cards: list[ItemId] = Field(max_length=20)
    suspended_accounts: list[ItemId] = Field(max_length=0, description="Always empty: no account suspension yet.")
    not_done: list[Code] = Field(max_length=20)
    next_steps: list[Code] = Field(max_length=20)
    policy_version: Code
    policy_rule: Code | None = None
    explanation_rule: Code | None = None
    narrative: str = Field(min_length=1, max_length=2000)
    narrative_source: Literal["llm", "template"]
    claim_issues: list[Issue] = Field(max_length=20)


class HandoffRecord(BaseModel):
    id: str
    customer_id: str
    verified: bool


class NotificationRecord(BaseModel):
    id: str
    ticket_id: str
    customer_id: str
    status: str
    verified: bool


class IdentityResult(BaseModel):
    # Same "failed" for an unknown customer and a wrong answer: no enumeration oracle.
    status: Literal["verified", "failed", "locked"]
    customer_id: str | None = None        # on "verified": internal ID, for the agent's traceability
    session_token: str | None = None
    product_numbers: list[str] = []
    # The server owns these limits; the agent shows them instead of keeping its own copies.
    attempts_left: int | None = None      # on "failed"
    locked_until: str | None = None       # ISO 8601 UTC, on "locked"
    expires_at: str | None = None         # ISO 8601 UTC token expiry, on "verified"


def decimal_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value if isinstance(value, Decimal) else Decimal(str(value)))


def iso_utc(value: dt.datetime) -> str:
    # BigQuery TIMESTAMP is UTC; be explicit if a client returns a naive value.
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.isoformat()


def to_transaction(row: dict[str, Any]) -> Transaction:
    return Transaction(
        id=row["transaction_id"],
        customer_id=row["customer_id"],
        card_id=row["product_id"] if row.get("product_type") in CARD_TYPES else None,
        status=row["transaction_status"],
        fraud_score=decimal_str(row["fraud_score"]),
        amount=decimal_str(row["amount"]),
        amount_usd=decimal_str(row["amount_usd"]),
        amount_usd_original=decimal_str(row.get("amount_usd_original", row["amount_usd"])),
        amount_usd_source=row.get("amount_usd_source", "curated" if row["amount_usd"] is not None else "unavailable"),
        fx_rate=decimal_str(row.get("fx_rate")), fx_date=row.get("fx_date"), fx_run_id=row.get("fx_run_id"),
        currency=row["currency"],
        date=iso_utc(row["transaction_date"]),
        local_date=str(row["local_date"]) if row.get("local_date") else None,
        customer_timezone=row.get("customer_timezone"),
        merchant=row.get("merchant_name"),
    )


def to_card(row: dict[str, Any]) -> Card:
    return Card(id=row["product_id"], customer_id=row["customer_id"], last4=row.get("last4"),
                status=row["product_status"], type=row["product_type"])


def to_search(rows: list[dict[str, Any]], limit: int) -> TransactionSearch:
    """Rows were fetched with limit + 1, so an extra row means the list is partial."""
    return TransactionSearch(transactions=[to_transaction(r) for r in rows[:limit]], has_more=len(rows) > limit)
