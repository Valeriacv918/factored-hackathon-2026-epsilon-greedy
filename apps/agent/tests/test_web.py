"""Web front (bank_agent.web): interrupts as forms and buttons, conversation ownership, metrics.

No network, MCP or model: a small graph with the same interrupt payloads stands in for the agent.
"""
import json
import logging
from typing import TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from starlette.testclient import TestClient

from bank_agent import observability as obs
from bank_agent.web.app import AgentApp, Pending, create_app, present, resume_value
from bank_agent.web.metrics import LiveMetrics, offline_triage, percentile

CARDS = [{"id": "PRD-SECRET-A", "last4": "1234"}, {"id": "PRD-SECRET-B", "last4": "1234"}]


class S(TypedDict, total=False):
    conversation_id: str
    session_ref: str
    message: str
    identity: dict
    card: str
    outcome: str
    response: str
    trace: list


def fake_graph():
    def login(s):
        value = interrupt({"kind": "identity_form", "language": "es", "message": "Verifica tu identidad.",
                           "fields": ["document_number", "date_of_birth", "product_number"]})
        return {"identity": value, "trace": [{"node": "validation_wait", "next": "card"}]}

    def card(s):
        value = interrupt({"kind": "select_card", "language": "es", "message": "Selecciona la tarjeta.",
                           "options": [c["id"] for c in CARDS] + ["human"], "cards": CARDS})
        return {"card": value["choice"], "outcome": "dispute_filed", "response": "Listo.",
                "trace": s["trace"] + [{"node": "card_emergency_agent", "next": "end"}]}

    builder = StateGraph(S)
    builder.add_node("login", login)
    builder.add_node("card", card)
    builder.add_edge(START, "login")
    builder.add_edge("login", "card")
    builder.add_edge("card", END)
    return builder.compile(checkpointer=InMemorySaver())


class FakeServices:
    def now(self):
        import datetime as dt
        return dt.datetime(2026, 6, 17, tzinfo=dt.timezone.utc)

    def close(self):
        pass


@pytest.fixture
def web():
    graph = fake_graph()
    agent = AgentApp(FakeServices(), graph)
    with TestClient(create_app(lambda: agent)) as client:
        yield client, agent, graph


# --- interrupts -> what the browser sees ------------------------------------------------------

def test_card_buttons_show_last4_and_never_the_product_id():
    view, pending = present({"kind": "select_card", "language": "es", "message": "Selecciona",
                             "options": [c["id"] for c in CARDS] + ["human"], "cards": CARDS})
    assert [o["label"] for o in view["options"]] == ["Tarjeta •••• 1234", "Tarjeta •••• 1234", "Hablar con un asesor"]
    assert "PRD-SECRET" not in json.dumps(view)
    assert pending.options[1] == "PRD-SECRET-B"   # the duplicate last4 still resolves to the right card


def test_transactions_show_date_amount_merchant_without_ids():
    view, _ = present({"kind": "select_transaction", "message": "Elige", "options": ["TX-9", "none", "human"],
                       "transactions": [{"id": "TX-9", "date": "2026-06-10T10:00:00", "amount": "40.00",
                                         "currency": "USD", "merchant": "Uber"}]})
    assert view["options"][0]["label"] == "2026-06-10 · 40.00 USD · Uber"
    assert "TX-9" not in json.dumps(view)


def test_unknown_option_values_are_not_shown_raw():
    view, _ = present({"kind": "x", "message": "?", "options": ["internal-code"]})
    assert view["options"][0]["label"] == "Opción 1" and "internal-code" not in json.dumps(view)


def test_identity_form_and_text_kinds():
    view, pending = present({"kind": "identity_form", "language": "pt", "message": "m",
                             "fields": ["document_number", "date_of_birth", "product_number"]})
    assert [f["label"] for f in view["form"]][0] == "Número do documento"
    assert view["form"][1]["type"] == "date" and pending.fields
    view, pending = present({"kind": "request_details", "message": "¿Qué necesitas?"})
    assert view["input"] == "text" and not pending.options and not pending.fields


def test_resume_values_are_validated_against_the_pending_question():
    assert resume_value(Pending("select_card", options=["A", "B"]), {"index": 1}) == {"choice": "B"}
    for bad in ({"index": 2}, {"index": True}, {"index": "0"}, {"choice": "A"}):
        with pytest.raises(ValueError):
            resume_value(Pending("select_card", options=["A", "B"]), bad)
    form = Pending("identity_form", fields=["document_number", "date_of_birth"])
    assert resume_value(form, {"fields": {"document_number": " 12 ", "date_of_birth": "1970-08-04"}}) == {
        "document_number": "12", "date_of_birth": "1970-08-04"}
    with pytest.raises(ValueError):
        resume_value(form, {"fields": {"document_number": "12"}})
    with pytest.raises(ValueError):
        resume_value(Pending("request_details"), {"text": "  "})


# --- HTTP -----------------------------------------------------------------------------------

def test_conversation_runs_through_form_and_buttons(web):
    client, agent, graph = web
    first = client.post("/api/conversations", json={"message": "Me robaron la billetera"}).json()
    assert first["status"] == "waiting" and first["question"]["kind"] == "identity_form"
    thread = first["thread_id"]
    second = client.post(f"/api/conversations/{thread}/resume", json={"fields": {
        "document_number": "E1", "date_of_birth": "1970-08-04", "product_number": "900"}}).json()
    assert second["question"]["kind"] == "select_card"
    assert "PRD-SECRET" not in json.dumps(second)
    done = client.post(f"/api/conversations/{thread}/resume", json={"index": 1}).json()
    assert done["status"] == "done" and done["group"] == "resolved"
    state = graph.get_state({"configurable": {"thread_id": thread}}).values
    assert state["card"] == "PRD-SECRET-B"
    # finished: no more answers accepted
    assert client.post(f"/api/conversations/{thread}/resume", json={"index": 0}).status_code == 400


def test_another_browser_cannot_resume_a_conversation(web):
    client, agent, _ = web
    thread = client.post("/api/conversations", json={"message": "hola"}).json()["thread_id"]
    client.cookies.clear()
    response = client.post(f"/api/conversations/{thread}/resume", json={"fields": {}})
    assert response.status_code == 404


def test_bad_answers_are_rejected_without_advancing(web):
    client, _, graph = web
    thread = client.post("/api/conversations", json={"message": "hola"}).json()["thread_id"]
    assert client.post(f"/api/conversations/{thread}/resume", json={"text": "1020 1970-08-04"}).status_code == 400
    assert graph.get_state({"configurable": {"thread_id": thread}}).values.get("identity") is None
    assert client.post("/api/conversations", json={"message": ""}).status_code == 400


def test_static_page_and_security_headers(web):
    client, _, _ = web
    page = client.get("/")
    assert page.status_code == 200 and "Epsilon Bank" in page.text
    assert 'id="ui-lang"' in page.text            # ES/PT toggle for the interface text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert client.get("/healthz").json() == {"ok": True}


def test_metrics_endpoint_aggregates_summaries(web):
    client, _, _ = web
    obs.log_summary("c-1", **obs.outcome_fields({"outcome": "escalated", "intent": "emergency", "language": "pt",
                                                  "queue": "cards", "priority": "P2", "ticket_id": "T-1",
                                                  "blocked_cards": ["PRD-SECRET-A"]}))
    data = client.get("/api/metrics").json()
    live = data["live"]
    assert live["conversations"] == 1 and live["tickets"]["total"] == 1
    assert live["tickets"]["by_queue"] == {"cards": 1} and live["actions"]["cards_blocked"] == 1
    assert live["containment"] == 0 and live["by_language"]["pt"]["conversations"] == 1
    assert "PRD-SECRET" not in json.dumps(data) and "T-1" not in json.dumps(data)
    assert data["scenario_date"] == "2026-06-17"


# --- metrics ----------------------------------------------------------------------------------

def test_live_metrics_groups_outcomes_latency_and_cost(monkeypatch):
    monkeypatch.setenv("LLM_PRICE_INPUT_PER_MTOK", "1")
    monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_MTOK", "2")
    live = LiveMetrics()
    record = logging.LogRecord("bank_agent.events", logging.INFO, "", 0, "", None, None)
    for outcome, step_ms in (("dispute_filed", 100), ("escalated", 300), ("out_of_scope", 200)):
        record.event_data = {"event": "conversation.summary", "outcome": outcome, "step_ms": step_ms,
                             "duration_ms": step_ms * 10, "input_tokens": 1000, "output_tokens": 500}
        live.emit(record)
    snap = live.snapshot()
    assert snap["outcomes"]["resolved"] == 1 and snap["outcomes"]["escalated"] == 1
    assert snap["outcomes"]["abstained"] == 1 and snap["containment"] == round(2 / 3, 3)
    assert snap["latency_ms"]["system_p50"] == 200 and snap["latency_ms"]["system_p95"] == 300
    assert snap["cost_usd"]["per_conversation"] == 0.002 and snap["cost_usd"]["per_resolved"] == 0.006


def test_percentile_and_empty_cost():
    assert percentile([], 50) is None and percentile([5], 95) == 5
    assert LiveMetrics().snapshot()["cost_usd"]["per_resolved"] is None   # "not defined" without resolutions


def test_offline_triage_reads_the_latest_run(tmp_path):
    (tmp_path / "triage_20260101_000000.csv").write_text("model,id,lang,ok,critical\nllm,a,es,0,1\n", encoding="utf-8")
    (tmp_path / "triage_20260102_000000.csv").write_text(
        "model,id,lang,ok,critical\nllm,a,es,1,0\nllm,b,es,0,0\nbaseline,a,es,0,1\nbaseline,b,es,1,0\n", encoding="utf-8")
    result = offline_triage(tmp_path)
    assert result["run"] == "triage_20260102_000000" and result["cases"] == 2
    llm = next(r for r in result["results"] if r["model"] == "llm")
    assert llm["accuracy"] == 0.5 and llm["critical"] == 0
    assert offline_triage(tmp_path / "missing") is None
