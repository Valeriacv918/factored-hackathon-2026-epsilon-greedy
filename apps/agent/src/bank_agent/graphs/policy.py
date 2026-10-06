"""Versioned demo policy from docs/state-machine.md, not a bank or legal policy."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bank_agent.nodes.common import number


@dataclass(frozen=True)
class Policy:
    version: str = "demo-v4"
    fraud_score: Decimal = Decimal("30")
    high_amount_usd: Decimal = Decimal("500")
    window_days: int = 90
    repeat_disputes: int = 2
    max_charges: int = 3
    max_clarifications: int = 2
    max_turns: int = 8
    intent_confidence: Decimal = Decimal("0.75")


def decide(tx, context, now, policy, fraud=False):
    if context.get("existing_case_id"):
        return "duplicate", "DSP-004"
    try:
        age = (now - datetime.fromisoformat(tx["date"])).total_seconds() / 86400
    except (ValueError, TypeError, KeyError):
        return "escalate", "missing_transaction_date"
    if age < 0:
        return "escalate", "future_transaction"
    if age > policy.window_days:
        return ("escalate" if fraud else "deny"), "DSP-005"
    amount = number(tx.get("amount_usd"))
    if amount is None or amount < 0:
        return "escalate", "missing_or_invalid_usd_amount"
    if not fraud:
        count = context.get("recent_dispute_count")
        if type(count) is not int or count < 0:
            return "escalate", "missing_dispute_history"
        if count >= policy.repeat_disputes:
            return "escalate", "DSP-011"
        if amount > policy.high_amount_usd:
            return "escalate", "DSP-012"
    return "file", "DSP-100"
