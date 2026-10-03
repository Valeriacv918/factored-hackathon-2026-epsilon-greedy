"""McpServices with a fake MCP client: no network, GCP or model."""
import datetime as dt
from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.clients.mcp_services import McpServices, detect_language_lingua, scenario_clock
from bank_agent.clients.sessions import StaticSessions
from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.state import initial_state

NOW = dt.datetime(2026, 6, 18, 12, tzinfo=dt.timezone.utc)
CARD = {"id": "PRD-1", "customer_id": "CLI-1", "last4": "1245", "status": "Active", "type": "Tarjeta Crédito"}
TX = {"id": "TRX-1", "customer_id": "CLI-1", "card_id": "PRD-1", "status": "Reversed", "fraud_score": "5.1",
      "amount": "329.6", "amount_usd": "329.6", "currency": "USD", "date": "2026-06-11T14:48:29+00:00",
      "merchant": "Internet Plus"}


class FakeMcpClient:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def call(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if self.fail:
            raise ServiceFailure(name)
        return deepcopy({"find_transactions": {"transactions": [TX], "has_more": False},
                         "list_cards": {"cards": [CARD]}, "get_card": CARD}[name])

    def close(self):
        pass


class StubUnderstanding:
    def __init__(self, intent):
        self.intent = intent

    def understand(self, text, language):
        return {"intent": self.intent, "confidence": 0.95, "slots": {"amount": "329.60"}, "wants_human": False}


def services(intent="charge_error", client=None):
    return McpServices(client or FakeMcpClient(), StaticSessions({"dev": "CLI-1"}), StubUnderstanding(intent),
                       clock=lambda: NOW, language_detector=lambda text: "es")


def test_customer_and_reference_date_come_from_adapter_not_arguments():
    s = services()
    s.tool("find_transactions", session_ref="dev", customer_id="CLI-1",
           arguments={"slots": {"amount": "1"}, "limit": 3, "customer_id": "CLI-OTHER", "reference_date": "2020-01-01"})
    assert s._client.calls == [("find_transactions", {"slots": {"amount": "1"}, "limit": 3,
                                                      "customer_id": "CLI-1", "reference_date": "2026-06-18"})]


def test_session_must_match_customer():
    with pytest.raises(SessionExpired):
        services().tool("list_cards", session_ref="dev", customer_id="CLI-OTHER", arguments={})
    with pytest.raises(SessionExpired):
        services().tool("list_cards", session_ref="unknown", customer_id="CLI-1", arguments={})


@pytest.mark.parametrize("name", ["block_card", "file_dispute", "dispute_context", "create_handoff", "run_query"])
def test_tools_not_offered_yet_fail_without_reaching_server(name):
    s = services()
    with pytest.raises(ServiceFailure):
        s.tool(name, session_ref="dev", customer_id="CLI-1", arguments={"card_id": "PRD-1"})
    assert s._client.calls == []


def test_scenario_clock_runs_from_start_and_requires_timezone():
    assert abs(scenario_clock(NOW)() - NOW) < dt.timedelta(seconds=5)
    with pytest.raises(ValueError):
        scenario_clock(dt.datetime(2026, 6, 18))


def run(s, message="No reconozco este cargo"):
    graph = build_graph(s, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t"}, "recursion_limit": 100}
    return graph, config, graph.invoke(initial_state("t", "dev", message), config)


def test_graph_explains_reversed_charge_end_to_end():
    s = services("charge_error")
    graph, config, state = run(s)
    assert state["__interrupt__"][0].value["kind"] == "explanation"
    state = graph.invoke(Command(resume={"choice": "understood"}), config)
    assert state["outcome"] == "explained"
    assert [name for name, _ in s._client.calls] == ["find_transactions"]


def test_graph_lost_card_reaches_confirmation_then_fails_safely_without_writes():
    s = services("emergency")
    graph, config, state = run(s, "Perdí mi tarjeta")
    assert state["__interrupt__"][0].value["kind"] == "confirm_block"
    state = graph.invoke(Command(resume={"choice": "yes"}), config)
    assert state["outcome"] == "service_unavailable"
    assert state["block_verified_at"] == {} and state["blocked_cards"] == []
    # get_card runs again because LangGraph re-executes the node on resume.
    assert [name for name, _ in s._client.calls] == ["list_cards", "get_card", "get_card"]


def test_server_failure_escalates_then_ends_safely():
    _, _, state = run(services(client=FakeMcpClient(fail=True)))
    assert state["outcome"] == "service_unavailable"
    assert state["reason"] == "tool_failure"


@pytest.mark.parametrize("text,language", [("Hola, necesito ayuda con mi tarjeta de crédito", "es"),
                                           ("Olá, preciso de ajuda com o meu cartão de crédito", "pt")])
def test_real_language_detector_is_wired(text, language):
    # The graph tests inject a fake detector; this one imports the real lingua path.
    assert detect_language_lingua(text) == language
