"""Structured JSON events: steps, LLM calls, MCP calls and the per-conversation summary.

The event names and fields are the contract shared with the MCP server and the
future HTTP endpoint. No network, GCP or model.
"""
import datetime as dt
import json
import logging
import sys
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent import observability as obs
from bank_agent.clients.contracts import ServiceFailure
from bank_agent.clients.mcp_client import McpToolClient
from bank_agent.clients.understanding import LlmUnderstanding
from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.state import initial_state

SERVER = str(Path(__file__).with_name("mcp_echo_server.py"))
NOW = dt.datetime(2026, 6, 18, 12, tzinfo=dt.timezone.utc)


def events(caplog, name=None):
    return [r.event_data for r in caplog.records
            if hasattr(r, "event_data") and (name is None or r.event_data["event"] == name)]


@pytest.fixture(autouse=True)
def capture(caplog, monkeypatch):
    monkeypatch.delenv("LOG_LLM_CONTENT", raising=False)
    caplog.set_level(logging.INFO, logger="bank_agent")
    obs.reset()
    yield
    obs.reset()


def usage_model(text="hola"):
    return FakeMessagesListChatModel(responses=[AIMessage(
        text, usage_metadata={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13})])


# --- log_event and context -------------------------------------------------------------

def test_log_event_carries_conversation_and_node(caplog):
    with obs.bind(conversation_id="c-1", node="fraud_agent"):
        obs.log_event("custom", a=1)
    [ev] = events(caplog, "custom")
    assert ev["service"] == "agent" and ev["conversation_id"] == "c-1" and ev["node"] == "fraud_agent"
    assert ev["a"] == 1
    obs.log_event("after")
    assert events(caplog, "after")[0]["conversation_id"] is None


def test_json_formatter_writes_one_json_object(caplog):
    with obs.bind(conversation_id="c-1"):
        obs.log_event("custom", amount="40.00")
    record = next(r for r in caplog.records if hasattr(r, "event_data"))
    line = json.loads(obs.JsonFormatter().format(record))
    assert line["event"] == "custom" and line["level"] == "INFO" and "ts" in line
    assert line["amount"] == "40.00"


def test_configure_logging_writes_to_log_file(tmp_path, monkeypatch):
    path = tmp_path / "agent.jsonl"
    monkeypatch.setenv("LOG_FILE", str(path))
    handler = obs.configure_logging()
    try:
        obs.log_event("to_file", x=1)
        handler.flush()
    finally:
        logging.getLogger("bank_agent").removeHandler(handler)
        handler.close()
    [line] = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert line["event"] == "to_file" and line["x"] == 1


def test_safe_args_redacts_identity_and_secrets():
    args = {"session_token": "tok", "document_number": "1020", "date_of_birth": "1990-04-03",
            "product_number": "4111", "card_id": "card-1",
            "packet": {"reason": "fraud", "queue": "fraud", "customer_quote": "mi cédula 1020"}}
    out = obs.safe_args(args)
    assert out["card_id"] == "card-1"
    assert {out[k] for k in ("session_token", "document_number", "date_of_birth", "product_number")} == {"<redacted>"}
    assert out["packet"] == {"reason": "fraud", "queue": "fraud"}


# --- LLM ---------------------------------------------------------------------------------

def test_llm_call_logs_metadata_without_content(caplog):
    with obs.bind(conversation_id="c-1"):
        usage_model().invoke([("user", "mi cédula 1020304050")], config=obs.llm_config("understanding"))
    [ev] = events(caplog, "llm.call")
    assert ev["step"] == "understanding" and ev["status"] == "ok" and ev["conversation_id"] == "c-1"
    assert ev["input_tokens"] == 10 and ev["output_tokens"] == 3 and ev["ms"] >= 0
    assert "messages" not in ev and "output" not in ev
    assert "1020304050" not in json.dumps(ev)


def test_llm_call_logs_content_with_flag(caplog, monkeypatch):
    monkeypatch.setenv("LOG_LLM_CONTENT", "1")
    usage_model("respuesta").invoke([("user", "hola")], config=obs.llm_config("triage"))
    [ev] = events(caplog, "llm.call")
    assert "hola" in json.dumps(ev["messages"], ensure_ascii=False)
    assert "respuesta" in json.dumps(ev["output"], ensure_ascii=False)


def test_llm_error_is_logged(caplog):
    with pytest.raises(Exception):
        FakeMessagesListChatModel(responses=[]).invoke([("user", "x")], config=obs.llm_config("narrative"))
    [ev] = events(caplog, "llm.call")
    assert ev["step"] == "narrative" and ev["status"] == "error" and ev["error"]


def test_understanding_logs_its_decision(caplog):
    class Stub:
        def invoke(self, messages):
            return {"intent": "not_me", "confidence": 0.9, "slots": {"merchant": "Uber"}}
    LlmUnderstanding(Stub(), lambda: NOW).understand("No reconozco Uber", "es")
    [ev] = events(caplog, "llm.result")
    assert ev["step"] == "understanding" and ev["intent"] == "not_me" and ev["confidence"] == 0.9
    assert ev["slots"] == {"merchant": "Uber"}


def test_summary_totals_llm_and_mcp_per_conversation(caplog):
    with obs.bind(conversation_id="c-1"):
        usage_model().invoke([("user", "x")], config=obs.llm_config("triage"))
        obs.log_event("mcp.call", tool="list_cards", ms=12.5, status="ok")
        obs.log_event("mcp.call", tool="get_card", ms=7.5, status="error")
    obs.log_summary("c-1")
    [ev] = events(caplog, "conversation.summary")
    assert ev["conversation_id"] == "c-1"
    assert ev["llm_calls"] == 1 and ev["input_tokens"] == 10 and ev["output_tokens"] == 3
    assert ev["mcp_calls"] == 2 and ev["mcp_ms"] == 20.0 and ev["errors"] == 1
    obs.log_summary("c-1")
    assert events(caplog, "conversation.summary")[1]["llm_calls"] == 0   # cleared after logging


# --- MCP client ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    with McpToolClient(command=sys.executable, args=[SERVER], timeout_s=5) as c:
        yield c


def test_mcp_call_sends_correlation_and_redacts_args(client, caplog):
    with obs.bind(conversation_id="c-1", node="fraud_agent"):
        out = client.call("meta", {"session_token": "tok-secret", "document_number": "1020", "card_id": "card-1"})
    assert out == {"conversation_id": "c-1", "node": "fraud_agent"}
    [ev] = events(caplog, "mcp.call")
    assert ev["tool"] == "meta" and ev["status"] == "ok" and ev["ms"] >= 0
    assert ev["args"]["card_id"] == "card-1"
    assert ev["args"]["session_token"] == ev["args"]["document_number"] == "<redacted>"
    assert "tok-secret" not in json.dumps(ev)


def test_mcp_error_text_reaches_the_log_not_the_caller(client, caplog):
    with pytest.raises(ServiceFailure) as exc:
        client.call("boom", {})
    assert "secret" not in str(exc.value)
    [ev] = events(caplog, "mcp.call")
    assert ev["status"] == "error" and "secret detail" in ev["error"]


# --- graph steps -----------------------------------------------------------------------------

def run_fraud_intake(services):
    graph = build_graph(services, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test"}, "recursion_limit": 100}
    graph.invoke(initial_state("conv-7", "trusted-session", "Cargo"), config)
    for choice in ("yes", "yes", "no"):
        state = graph.invoke(Command(resume={"choice": choice}), config)
    return state


def test_graph_logs_each_step_and_one_summary(fake_services, caplog):
    state = run_fraud_intake(fake_services())
    assert state["outcome"] == "fraud_intake_complete"
    steps = events(caplog, "step")
    assert steps and all(s["conversation_id"] == "conv-7" and s["ms"] >= 0 for s in steps)
    assert [s["node"] for s in steps][0] == "validator_agent"
    assert {"node", "phase", "next"} <= set(steps[0])
    [summary] = events(caplog, "conversation.summary")
    assert summary["conversation_id"] == "conv-7" and summary["steps"] == len(steps)


def test_step_is_logged_when_a_node_raises(fake_services, caplog):
    graph = build_graph(fake_services(language="en"), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t"}, "recursion_limit": 100}
    graph.invoke(initial_state("conv-8", "trusted-session", "Cargo"), config)
    with pytest.raises(ValueError):
        graph.invoke(Command(resume={"choice": "en"}), config)
    assert any(s.get("error") == "ValueError" for s in events(caplog, "step"))


def test_validation_triage_graph_logs_steps(caplog):
    from test_validation_triage_graph import Services, start
    start(Services(), cid="conv-9")
    steps = events(caplog, "step")
    assert steps and steps[0]["node"] == "validator_agent" and steps[0]["conversation_id"] == "conv-9"
