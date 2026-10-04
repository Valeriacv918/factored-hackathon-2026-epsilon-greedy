"""ChatService and API over the real dispute graph with synthetic services. No network or model."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.graphs.disputes import build_graph
from bank_web.chat import BadRequest, ChatService
from bank_web.main import create_app

SESSION = "validator-session"


class Services:
    def __init__(self, intent):
        self.intent, self.valid = intent, True
        self.cards = [{"id": "card-1", "customer_id": "customer-1", "last4": "1234", "status": "Active"}]

    def now(self):
        return datetime(2026, 10, 2, 12, tzinfo=timezone.utc)

    def detect_language(self, text):
        return "es"

    def validate_session(self, session_ref):
        return "customer-1" if self.valid and session_ref == SESSION else None

    def understand(self, text, language):
        return {"intent": self.intent, "confidence": 0.99, "slots": {}}

    def write_narrative(self, facts, language):
        raise ServiceFailure("no model")

    def tool(self, name, *, session_ref, customer_id, arguments):
        if name == "list_cards":
            return {"cards": self.cards}
        if name == "get_card":
            return self.cards[0]
        if name == "find_transactions":
            return {"transactions": []}
        raise ServiceFailure(f"{name} not available")


class StubAuth:
    """Stands in for ValidationAgent: 'ok' authenticates, 'lock' hands off."""

    def __init__(self):
        self.session = SimpleNamespace(session_id=SESSION, language="es")

    def chat(self, text):
        step = {"ok": "triage", "lock": "handoff_human"}.get(text, "ask_user")
        return {"reply": f"auth:{text}", "language": "es", "next_step": step}


def service(intent="emergency"):
    services = Services(intent)
    return ChatService(build_graph(services, checkpointer=InMemorySaver()), StubAuth), services


def authenticated(intent="emergency"):
    chats, services = service(intent)
    chat_id, _ = chats.start()
    assert chats.send(chat_id, text="ok")["phase"] == "dispute"
    return chats, services, chat_id


def test_auth_until_validator_says_triage():
    chats, _ = service()
    chat_id, welcome = chats.start()
    assert welcome["phase"] == "auth" and welcome["input"] == "text"
    reply = chats.send(chat_id, text="hola")
    assert reply == {"messages": ["auth:hola"], "phase": "auth", "input": "text", "options": [],
                     "details": {}, "outcome": None}
    assert chats.send(chat_id, text="ok")["phase"] == "dispute"


def test_locked_identity_ends_with_handoff():
    chats, _ = service()
    chat_id, _ = chats.start()
    reply = chats.send(chat_id, text="lock")
    assert reply["phase"] == "done" and reply["outcome"] == "handoff_human"
    with pytest.raises(BadRequest):
        chats.send(chat_id, text="hola")


def test_buttons_come_from_interrupt_and_are_enforced():
    chats, _, chat_id = authenticated("emergency")
    reply = chats.send(chat_id, text="perdí mi tarjeta")
    assert reply["input"] == "buttons"
    assert [o["value"] for o in reply["options"]] == ["yes", "no", "human"]
    assert reply["options"][0]["label"] == "Sí"
    with pytest.raises(BadRequest):
        chats.send(chat_id, choice="maybe")
    with pytest.raises(BadRequest):
        chats.send(chat_id, text="sí")   # free text never confirms an action
    final = chats.send(chat_id, choice="no")
    assert final["phase"] == "done" and final["input"] == "none" and final["messages"]


def test_clarification_accepts_text_only():
    chats, _, chat_id = authenticated("not_me")
    reply = chats.send(chat_id, text="no reconozco un cargo")
    assert reply["input"] == "text" and reply["phase"] == "dispute"
    with pytest.raises(BadRequest):
        chats.send(chat_id, choice="yes")
    assert chats.send(chat_id, text="ayer, 40 dólares")["phase"] in {"dispute", "done"}


def test_expired_session_goes_back_to_auth():
    chats, services, chat_id = authenticated("emergency")
    chats.send(chat_id, text="perdí mi tarjeta")
    services.valid = False
    reply = chats.send(chat_id, choice="yes")
    assert reply["phase"] == "auth" and reply["outcome"] == "authentication_required"
    assert chats.send(chat_id, text="hola")["messages"] == ["auth:hola"]


def test_api_uses_cookie_and_rejects_unknown_chat():
    chats, _ = service()
    with TestClient(create_app(chats)) as client:
        assert client.post("/api/chat", json={"text": "hola"}).status_code == 409
        start = client.post("/api/start")
        assert start.status_code == 200 and "chat_id" in start.cookies
        assert client.post("/api/chat", json={"text": "ok"}).json()["phase"] == "dispute"
        assert client.post("/api/chat", json={"choice": "yes"}).status_code == 400
        assert client.get("/").status_code == 200
