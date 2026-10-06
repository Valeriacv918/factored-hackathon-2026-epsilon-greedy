"""Exercise the real form adapter; mock only the MCP wire and LLM."""
import datetime as dt
import pytest
from starlette.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from bank_agent.clients.mcp_services import McpServices
from bank_agent.clients.sessions import StaticSessions
from bank_agent.graphs.validation_triage import build_graph
from bank_agent.web.app import AgentApp, create_app

FORM = {"document_number": "12345678", "date_of_birth": "1990-01-02", "product_number": "1234567890"}

class Wire:
    def __init__(self):
        self.calls = []
    def call(self, name, arguments):
        self.calls.append((name, arguments.copy()))
        assert name == "verify_identity", "No product access before authentication"
        if arguments != FORM:
            return {"status": "failed", "attempts_left": 2}
        return {"status": "verified", "customer_id": "CLI-TEST",
                "session_token": "synthetic-token", "product_numbers": ["1234567890"],
                "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15)).isoformat()}
    def close(self):
        pass

class NoLLM:
    def understand(self, *args):
        raise AssertionError("Identity must not invoke an LLM")

@pytest.mark.parametrize("language", ["es", "pt"])
def test_language_form_retry_and_mcp_session_grant(language):
    wire = Wire()
    services = McpServices(wire, StaticSessions({}), NoLLM(), language_detector=lambda text: None)
    graph = build_graph(services, checkpointer=InMemorySaver(), test_charge_error=True,
                        test_fraud=True, test_escalation=True, test_card_emergency=True)
    agent = AgentApp(services, graph)
    with TestClient(create_app(lambda: agent)) as web:
        first = web.post("/api/conversations", json={"message": "Oi"}).json()
        assert first["question"]["kind"] == "language"
        assert wire.calls == []
        index = next(o["index"] for o in first["question"]["options"] if o["value"] == language)
        endpoint = "/api/conversations/" + first["thread_id"] + "/resume"
        form = web.post(endpoint, json={"index": index}).json()
        assert form["question"]["kind"] == "identity_form"
        assert form["question"]["language"] == language
        assert [f["name"] for f in form["question"]["form"]] == list(FORM)
        assert wire.calls == []
        wrong = {**FORM, "product_number": "9999999999"}
        retry = web.post(endpoint, json={"fields": wrong}).json()
        assert retry["question"]["kind"] == "identity_form"
        assert retry["question"]["language"] == language
        assert len(wire.calls) == 1
        result = web.post(endpoint, json={"fields": FORM}).json()
        assert result["question"]["kind"] == "request_details"
        assert result["question"]["language"] == language
        assert len(wire.calls) == 2  # one call per submitted form, no replay
        assert wire.calls[-1] == ("verify_identity", FORM)
        state = graph.get_state({"configurable": {"thread_id": first["thread_id"]}}).values
        assert state["authenticated"] is True
        assert state["identity_prompts"] == 1
        assert services.validate_session(state["session_ref"]) == "CLI-TEST"
        assert FORM["document_number"] not in str(result)
        assert "synthetic-token" not in str(result)
