"""validator_agent como primer nodo del grafo de disputas: idioma, login con FORMULARIO y solicitud.

El login no usa LLM: los tres factores llegan en campos separados a services.verify_identity
(IdentityValidator -> MCP verify_identity). Principio: el LLM nunca ve datos personales.
"""
import base64
import datetime as dt
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent.clients.mcp_services import McpServices
from bank_agent.clients.sessions import StaticSessions
from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.state import initial_state
from bank_agent.nodes.triage_agent.schemas import Understanding
from conftest import FakeServices

GOOD = {"document_number": "1020304050", "date_of_birth": "1990-04-03", "product_number": "4111222233334444"}
WRONG = {**GOOD, "date_of_birth": "1991-01-01"}


class LoginServices(FakeServices):
    """verify_identity simulado con las mismas respuestas que IdentityValidator (sin datos del cliente)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.valid = False            # sin sesión: hay que hacer login
        self.down = False
        self.failures = 0
        self.forms = []

    def verify_identity(self, conversation_id, document_number, date_of_birth, product_number):
        self.calls.append("verify_identity")
        self.forms.append(conversation_id)
        if self.down:
            raise RuntimeError("MCP unavailable")
        if document_number == "lock":
            return {"status": "LOCKED", "attempts_left": None, "missing_fields": [], "session_ref": "s"}
        if not date_of_birth:
            return {"status": "MISSING_FIELDS", "attempts_left": None, "missing_fields": ["date_of_birth"], "session_ref": "s"}
        if date_of_birth == "31/02/1990":
            return {"status": "INVALID_FORMAT", "attempts_left": None, "missing_fields": ["date_of_birth"], "session_ref": "s"}
        if (document_number, date_of_birth, product_number) == tuple(GOOD.values()):
            self.valid = True
            return {"status": "VERIFIED", "attempts_left": None, "missing_fields": [], "session_ref": "trusted-session"}
        self.failures += 1
        return {"status": "FAILED", "attempts_left": 3 - self.failures, "missing_fields": [], "session_ref": "s"}


def start(services, message="Hola, perdí mi tarjeta"):
    graph = build_graph(services, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t"}, "recursion_limit": 100}
    return graph, config, graph.invoke(initial_state("t", "no-session", message), config)


def pause(state):
    return state["__interrupt__"][0].value


def test_login_form_then_request_then_dispute_flow():
    services = LoginServices()
    graph, config, state = start(services)
    form = pause(state)
    assert form["kind"] == "identity_form" and form["fields"] == ["document_number", "date_of_birth", "product_number"]
    state = graph.invoke(Command(resume=GOOD), config)
    assert pause(state)["kind"] == "request_details"
    assert "understand" not in services.calls                   # ningún LLM antes ni durante el login
    state = graph.invoke(Command(resume={"text": "No reconozco un cargo"}), config)
    assert pause(state)["kind"] == "confirm_block"              # llegó a fraud_agent
    assert state["customer_id"] == "customer-1" and state["session_ref"] == "trusted-session"
    assert state["message"] == "No reconozco un cargo"          # la solicitud, no el primer mensaje
    assert not any(v in str({k: v for k, v in state.items() if k != "trace"}) for v in GOOD.values())


def test_first_message_is_never_classified():
    """Puede traer datos de identidad: el triage solo ve la solicitud escrita después del login."""
    services = LoginServices()
    graph, config, _ = start(services, message="Mi documento es 1020304050 y perdí mi tarjeta")
    graph.invoke(Command(resume=GOOD), config)
    assert "understand" not in services.calls


def test_wrong_data_shows_the_form_again_with_attempts_left_then_verifies():
    services = LoginServices()
    graph, config, _ = start(services)
    state = graph.invoke(Command(resume=WRONG), config)
    form = pause(state)
    assert form["kind"] == "identity_form" and "Te quedan 2 intentos" in form["message"]
    assert "fecha" not in form["message"]                       # nunca dice cuál dato falló
    state = graph.invoke(Command(resume=GOOD), config)
    assert pause(state)["kind"] == "request_details"


def test_invalid_format_names_the_field_to_fix():
    services = LoginServices()
    graph, config, _ = start(services)
    state = graph.invoke(Command(resume={**GOOD, "date_of_birth": "31/02/1990"}), config)
    assert "fecha de nacimiento" in pause(state)["message"]


def test_portuguese_messages():
    services = LoginServices(language="pt")
    graph, config, state = start(services, message="Olá, perdi meu cartão")
    assert "identidade" in pause(state)["message"]
    state = graph.invoke(Command(resume=WRONG), config)
    assert "Os dados não conferem" in pause(state)["message"]


def test_locked_identity_ends_without_reading_data():
    services = LoginServices()
    graph, config, _ = start(services)
    state = graph.invoke(Command(resume={**GOOD, "document_number": "lock"}), config)
    assert state["outcome"] == "human_required"
    assert not any(c in services.calls for c in ("understand", "find_transactions", "list_cards"))


def test_identity_service_down_never_authenticates():
    services = LoginServices(); services.down = True
    graph, config, _ = start(services)
    state = graph.invoke(Command(resume=GOOD), config)
    assert state["outcome"] == "service_unavailable" and not state.get("customer_id")


def test_too_many_forms_end_with_a_human():
    services = LoginServices()
    graph, config, _ = start(services)
    for _ in range(6):
        state = graph.invoke(Command(resume={**GOOD, "date_of_birth": "31/02/1990"}), config)
    assert state["outcome"] == "human_required" and services.calls.count("verify_identity") == 6


def test_resuming_the_form_verifies_once():
    services = LoginServices()
    graph, config, _ = start(services)
    graph.invoke(Command(resume=GOOD), config)
    assert services.calls.count("verify_identity") == 1


@pytest.mark.parametrize("bad", [{"text": "1020304050 1990-04-03 4111"}, {**GOOD, "extra": "x"},
                                 {**GOOD, "product_number": 4111222233334444}])
def test_only_the_three_form_fields_are_accepted(bad):
    services = LoginServices()
    graph, config, _ = start(services)
    with pytest.raises(ValueError):
        graph.invoke(Command(resume=bad), config)
    assert "verify_identity" not in services.calls


def test_already_authenticated_session_skips_login():
    services = FakeServices()   # sesión válida (como la web app o DEV_SESSIONS)
    graph = build_graph(services, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t"}, "recursion_limit": 100}
    state = graph.invoke(initial_state("t", "trusted-session", "No reconozco un cargo"), config)
    assert pause(state)["kind"] == "confirm_block"


def test_services_without_login_ask_to_sign_in():
    services = FakeServices(); services.valid = False   # sin verify_identity
    graph = build_graph(services, checkpointer=InMemorySaver())
    state = graph.invoke(initial_state("t", "no-session", "Hola"), {"configurable": {"thread_id": "t"}})
    assert state["outcome"] == "authentication_required"


# ---------- con el McpServices REAL y un MCP simulado ----------

def _token(customer_id):
    payload = base64.urlsafe_b64encode(json.dumps({"sub": customer_id}).encode()).rstrip(b"=").decode()
    return f"{payload}.fake-signature"


class FakeMcp:
    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "verify_identity":
            expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15)
            return {"status": "verified", "customer_id": "CLI-1", "session_token": _token("CLI-1"),
                    "product_numbers": ["4111222233334444"], "expires_at": expires.isoformat()}
        return {"transactions": [], "has_more": False}

    def close(self):
        pass


class NoLlm:
    """Cualquier llamada a un LLM durante el login hace fallar el test."""
    def understand(self, *args, **kwargs):
        raise AssertionError("an LLM was called")


def test_real_mcp_services_login_form_sends_factors_only_to_the_mcp():
    mcp = FakeMcp()
    services = McpServices(mcp, StaticSessions({}), NoLlm(), language_detector=lambda text: "es")
    services._triage_classifier = type("T", (), {"understand": lambda self, text: Understanding(
        intent="other", confidence=0.99, wants_human=False)})()
    graph = build_graph(services, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t"}, "recursion_limit": 100}
    state = graph.invoke(initial_state("t", "no-session", "Hola, perdí mi tarjeta"), config)
    state = graph.invoke(Command(resume=GOOD), config)
    assert pause(state)["kind"] == "request_details"
    assert mcp.calls == [("verify_identity", GOOD)]             # los factores solo van al MCP
    assert services._validation_agents == {}                    # el agente conversacional (LLM) no se creó
    assert state["customer_id"] == "CLI-1"
