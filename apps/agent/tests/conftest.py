"""Synthetic in-memory services. No network, GCP, model, or banking operations."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from bank_agent.clients.contracts import ServiceFailure



class FakeServices:
    def __init__(self, *, language="es", intent="not_me", status="Approved", score="12"):
        self.language, self.intent = language, intent
        self.valid = True
        self.calls = []
        self.fail = set()
        self.timeout_after_write = set()
        self.records = {}
        self.confidence = 0.99
        self.narrative = None   # None: no model (template). str, or callable(facts) -> str.
        self.narrative_facts = None
        self.existing = None
        self.cards = [{"id": "card-1", "customer_id": "customer-1", "last4": "1234", "status": "Active"}]
        self.transactions = [{"id": "tx-1", "customer_id": "customer-1", "card_id": "card-1",
                              "status": status, "fraud_score": score, "amount": "40.00",
                              "amount_usd": "40.00", "currency": "USD", "date": "2026-09-30T12:00:00+00:00"}]


    def now(self):
        return datetime(2026, 10, 2, 12, tzinfo=timezone.utc)

    def detect_language(self, text):
        self.calls.append("detect_language")
        return self.language

    def validate_session(self, session_ref):
        self.calls.append("validate_session")
        return "customer-1" if self.valid and session_ref == "trusted-session" else None

    def understand(self, text, language):
        self.calls.append("understand")
        return {"intent": self.intent, "confidence": self.confidence, "slots": {}}

    def tool(self, name, *, session_ref, customer_id, arguments):
        assert self.validate_session(session_ref) == customer_id
        self.calls.append(name)
        if name in self.fail:
            raise ServiceFailure(name)
        if name == "find_transactions":
            return {"transactions": deepcopy(self.transactions)}
        if name == "list_cards":
            return {"cards": deepcopy(self.cards)}
        if name == "get_card":
            return deepcopy(next(c for c in self.cards if c["id"] == arguments["card_id"]))
        if name == "dispute_context":
            return {"existing_case_id": self.existing, "recent_dispute_count": 0}
        if name.startswith("read_"):
            return deepcopy(next(r for r in self.records.values() if r["id"] == arguments["id"]))
        key = arguments["idempotency_key"]
        if key not in self.records:
            record = {"id": f"receipt-{len(self.records) + 1}", "verified": True, "customer_id": customer_id}
            if name == "block_card":
                card = next(c for c in self.cards if c["id"] == arguments["card_id"])
                card["status"] = "Blocked"
                record.update(card_id=card["id"], status="Blocked")
            elif name == "file_dispute":
                record["transaction_id"] = arguments["transaction_id"]
            elif name == "notify_employee":
                record["ticket_id"] = arguments["ticket_id"]
            elif name != "create_handoff":
                raise AssertionError(name)
            self.records[key] = record
            if name in self.timeout_after_write:
                raise ServiceFailure("Committed but response lost")
        return deepcopy(self.records[key])

    def write_narrative(self, facts, language):
        self.calls.append("write_narrative")
        self.narrative_facts = deepcopy(facts)
        if self.narrative is None:
            raise ServiceFailure("no narrative model")
        return self.narrative(facts) if callable(self.narrative) else self.narrative

@pytest.fixture
def fake_services():
    """Factory: call as fake_services(language="pt", intent=...)."""
    return FakeServices
