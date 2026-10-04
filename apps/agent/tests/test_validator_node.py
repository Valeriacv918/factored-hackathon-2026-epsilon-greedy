"""validator_agent como primer nodo del grafo de disputas: idioma, login y solicitud."""
from types import SimpleNamespace

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.state import initial_state
from conftest import FakeServices


class FakeValidationAgent:
    """Verifica cuando el texto trae 'ok'; se bloquea con 'lock'. Como el validador real:
    la decisión viene de next_step, no del texto del LLM."""

    def __init__(self, services):
        self.services, self.session = services, SimpleNamespace(session_id="trusted-session")
        self.texts = []

    def chat(self, text):
        self.texts.append(text)
        if "lock" in text:
            return {"status": "LOCKED", "next_step": "handoff_human", "reply": "Bloqueado."}
        if "ok" in text:
            self.services.valid = True
            return {"status": "VERIFIED", "next_step": "triage", "reply": "Verificado."}
        return {"status": "MISSING_FIELDS", "next_step": "ask_user", "reply": "Indica tu documento."}


class LoginServices(FakeServices):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.valid = False   # sin sesión: hay que hacer login
        self.agent = FakeValidationAgent(self)

    def validation_agent(self, conversation_id):
        return self.agent


def start(services, message="Hola"):
    graph = build_graph(services, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t"}, "recursion_limit": 100}
    return graph, config, graph.invoke(initial_state("t", "no-session", message), config)


def test_login_then_request_then_dispute_flow():
    services = LoginServices()
    graph, config, state = start(services)
    assert state["__interrupt__"][0].value["kind"] == "validation_details"
    state = graph.invoke(Command(resume={"text": "doc 1020304050 ok"}), config)
    assert state["__interrupt__"][0].value["kind"] == "request_details"
    assert "understand" not in services.calls          # no clasifica antes de autenticar
    state = graph.invoke(Command(resume={"text": "No reconozco un cargo"}), config)
    assert state["__interrupt__"][0].value["kind"] == "confirm_block"   # llegó a fraud_agent
    assert state["customer_id"] == "customer-1" and state["session_ref"] == "trusted-session"
    assert state["message"] == "No reconozco un cargo"                  # la solicitud, no los datos de identidad
    assert "1020304050" not in str({k: v for k, v in state.items() if k != "trace"})


def test_locked_identity_ends_without_reading_data():
    services = LoginServices()
    graph, config, state = start(services)
    state = graph.invoke(Command(resume={"text": "lock"}), config)
    assert state["outcome"] == "human_required"
    assert not any(c in services.calls for c in ("understand", "find_transactions", "list_cards"))


def test_already_authenticated_session_skips_login():
    services = FakeServices()   # sesión válida (como la web app o DEV_SESSIONS)
    graph = build_graph(services, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t"}, "recursion_limit": 100}
    state = graph.invoke(initial_state("t", "trusted-session", "No reconozco un cargo"), config)
    assert state["__interrupt__"][0].value["kind"] == "confirm_block"