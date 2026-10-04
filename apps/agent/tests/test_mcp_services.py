"""McpServices with a fake MCP client: no network, GCP or model."""
import base64
import datetime as dt
import json
from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.clients.mcp_services import McpServices, detect_language_lingua, scenario_clock
from bank_agent.clients.sessions import StaticSessions
from bank_agent.config.settings import FraudPolicy
from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.policy import Policy
from bank_agent.graphs.state import initial_state
from bank_agent.nodes.triage_agent.schemas import Understanding

NOW = dt.datetime(2026, 6, 18, 12, tzinfo=dt.timezone.utc)
CARD = {"id": "PRD-1", "customer_id": "CLI-1", "last4": "1245", "status": "Active", "type": "Tarjeta Crédito"}
TX = {"id": "TRX-1", "customer_id": "CLI-1", "card_id": "PRD-1", "status": "Reversed", "fraud_score": "5.1",
      "amount": "329.6", "amount_usd": "329.6", "currency": "USD", "date": "2026-06-11T14:48:29+00:00",
      "merchant": "Internet Plus"}


def dev_token(customer_id):
    """Token-shaped string. The fake client does not check signatures; the real server does."""
    payload = base64.urlsafe_b64encode(json.dumps({"sub": customer_id}).encode()).rstrip(b"=").decode()
    return f"{payload}.fake-signature"


TOKEN = dev_token("CLI-1")
BLOCK = {"id": "BLK-1", "card_id": "PRD-1", "customer_id": "CLI-1", "status": "Blocked", "verified": True}


class FakeMcpClient:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def call(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if self.fail:
            raise ServiceFailure(name)
        return deepcopy({"find_transactions": {"transactions": [TX], "has_more": False},
                         "list_cards": {"cards": [CARD]}, "get_card": CARD,
                         "block_card": {"id": "BLK-1"}, "read_block": BLOCK}[name])

    def close(self):
        pass

class StubTriage:
    """Triage classifier stand-in: unit tests never call Groq."""

    def __init__(self, intent):
        self.intent = intent

    def understand(self, text):
        return Understanding(intent=self.intent, confidence=0.99, wants_human=False)

class StubUnderstanding:
    def __init__(self, intent):
        self.intent = intent

    def understand(self, text, language):
        return {"intent": self.intent, "confidence": 0.95, "slots": {"amount": "329.60"}, "wants_human": False}


def services(intent="charge_error", client=None):
    services = McpServices(client or FakeMcpClient(), StaticSessions({"dev": TOKEN}), StubUnderstanding(intent),
                       clock=lambda: NOW, language_detector=lambda text: "es")
    services._triage_classifier = StubTriage(intent)   # sin Groq en tests unitarios
    return services



def test_session_token_and_reference_date_come_from_adapter_not_arguments():
    s = services()
    s.tool("find_transactions", session_ref="dev", customer_id="CLI-1",
           arguments={"slots": {"amount": "1"}, "limit": 3, "customer_id": "CLI-OTHER",
                      "session_token": "forged", "reference_date": "2020-01-01"})
    # The server learns the customer only from the token; no customer_id is sent.
    assert s._client.calls == [("find_transactions", {"slots": {"amount": "1"}, "limit": 3,
                                                      "session_token": TOKEN, "reference_date": "2026-06-18"})]


def test_validate_session_returns_token_customer():
    assert services().validate_session("dev") == "CLI-1"
    assert services().validate_session("unknown") is None


def test_session_must_match_customer():
    with pytest.raises(SessionExpired):
        services().tool("list_cards", session_ref="dev", customer_id="CLI-OTHER", arguments={})
    with pytest.raises(SessionExpired):
        services().tool("list_cards", session_ref="unknown", customer_id="CLI-1", arguments={})


@pytest.mark.parametrize("name", ["create_handoff", "notify_employee", "suspend_account_transactions", "run_query",
                                  "verify_identity"])
def test_tools_not_offered_yet_fail_without_reaching_server(name):
    s = services()
    with pytest.raises(ServiceFailure):
        s.tool(name, session_ref="dev", customer_id="CLI-1", arguments={"card_id": "PRD-1"})
    assert s._client.calls == []


def test_writes_send_only_allow_listed_arguments_and_the_token():
    s = services()
    s.tool("block_card", session_ref="dev", customer_id="CLI-1",
           arguments={"card_id": "PRD-1", "idempotency_key": "t:block_card:PRD-1", "customer_id": "CLI-OTHER",
                      "scenario_id": "forged", "session_token": "forged"})
    assert s._client.calls == [("block_card", {"card_id": "PRD-1", "idempotency_key": "t:block_card:PRD-1",
                                               "session_token": TOKEN})]


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


def test_graph_lost_card_blocks_and_verifies_through_the_server():
    s = services("emergency")
    graph, config, state = run(s, "Perdí mi tarjeta")
    assert state["__interrupt__"][0].value["kind"] == "confirm_block"
    state = graph.invoke(Command(resume={"choice": "yes"}), config)
    assert state["__interrupt__"][0].value["kind"] == "unrecognized_charge"
    assert state["blocked_cards"] == ["PRD-1"] and set(state["block_verified_at"]) == {"PRD-1"}
    # get_card runs again because LangGraph re-executes the node on resume.
    assert [name for name, _ in s._client.calls] == ["list_cards", "get_card", "get_card", "block_card", "read_block"]
    assert s._client.calls[3][1] == {"card_id": "PRD-1", "idempotency_key": "t:block_card:PRD-1", "session_token": TOKEN}
    assert s._client.calls[4][1] == {"id": "BLK-1", "session_token": TOKEN}


def test_server_failure_escalates_then_ends_safely():
    _, _, state = run(services(client=FakeMcpClient(fail=True)))
    assert state["outcome"] == "service_unavailable"
    assert state["reason"] == "tool_failure"


@pytest.mark.parametrize("text,language", [("Hola, necesito ayuda con mi tarjeta de crédito", "es"),
                                           ("Olá, preciso de ajuda com o meu cartão de crédito", "pt")])
def test_real_language_detector_is_wired(text, language):
    # The graph tests inject a fake detector; this one imports the real lingua path.
    assert detect_language_lingua(text) == language


def test_graph_sends_its_own_policy_window_to_the_server():
    s = services("charge_error")
    graph = build_graph(s, checkpointer=InMemorySaver(), policy=Policy(window_days=30))
    graph.invoke(initial_state("t", "dev", "No reconozco este cargo"),
                 {"configurable": {"thread_id": "t"}, "recursion_limit": 100})
    assert s._client.calls[0][0] == "find_transactions"
    assert s._client.calls[0][1]["window_days"] == 30


def test_fraud_policy_reads_the_graph_policy():
    graph, fraud = Policy(), FraudPolicy()
    assert fraud.dispute_window_days == graph.window_days
    assert fraud.fraud_score_threshold == float(graph.fraud_score)
    assert fraud.high_amount_usd_threshold == float(graph.high_amount_usd)
    assert fraud.max_charges_per_case == graph.max_charges
