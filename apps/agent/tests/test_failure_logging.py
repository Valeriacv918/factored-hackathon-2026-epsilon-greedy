"""Every path that turns a failure into service_unavailable leaves a `service.failure` event.

The event names the reason and our own error message; the cause is logged by type only,
because its text can carry customer input (pydantic echoes the invalid value).
"""
import json
import logging

import pytest
from langgraph.types import Command
from pydantic import ValidationError

from bank_agent import observability as obs
from bank_agent.clients.contracts import ServiceFailure
from bank_agent.clients.understanding import Slots
from test_charge_test_graph import ChargeServices, TX, start as start_charge
from test_escalation_handoff import escalate_high_score
from test_graph import start as start_disputes, resume
from test_validation_triage_graph import Services, start as start_triage, authenticate
from test_validator_node import GOOD, LoginServices, start as start_validator

SECRET = "SECRET-CUSTOMER-TEXT"


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


def only_failure(caplog):
    [ev] = events(caplog, "service.failure")
    return ev


def test_charge_receipt_failure_is_logged_with_its_reason(caplog):
    s = ChargeServices(); s.bad_receipt = True
    g, c, _ = start_charge(s)
    state = g.invoke(Command(resume={"choice": "TX-1"}), c)
    assert state["outcome"] == "service_unavailable" and state["reason"] == "charge_tool_failure"
    ev = only_failure(caplog)
    assert ev["reason"] == "charge_tool_failure" and ev["node"] == "charge_save"
    assert ev["error"] == "ServiceFailure" and ev["detail"] == "Explanation receipt not verified"
    [summary] = events(caplog, "conversation.summary")
    assert summary["reason"] == "charge_tool_failure" and summary["failures"] == 1


def test_failure_is_not_counted_again_as_a_tool_error(caplog):
    class LlmDown(ChargeServices):
        def understand(self, text, language):
            obs.log_event("llm.call", step="understanding", status="error", error="AuthenticationError")
            raise ServiceFailure("Understanding unavailable")

    start_charge(LlmDown())
    [summary] = events(caplog, "conversation.summary")
    assert summary["errors"] == 1 and summary["failures"] == 1


def test_cause_is_logged_by_type_never_by_text(caplog):
    class BadExtraction(ChargeServices):
        def understand(self, text, language):
            try:
                Slots.model_validate({"amount": SECRET})
            except ValidationError as exc:
                raise ServiceFailure("Invalid extraction schema") from exc

    _, _, state = start_charge(BadExtraction())
    assert state["outcome"] == "service_unavailable"
    ev = only_failure(caplog)
    assert ev["node"] == "charge_extract" and ev["detail"] == "Invalid extraction schema"
    assert ev["cause"] == "ValidationError"
    assert SECRET not in json.dumps(events(caplog), default=str)


def test_validation_outage_is_logged(caplog):
    s = Services(); s.broken = True
    g, c, _ = start_triage(s)
    authenticate(g, c)
    ev = only_failure(caplog)
    assert ev["reason"] == "validation_unavailable" and ev["error"] == "RuntimeError" and ev["detail"] == "unavailable"


def test_triage_failure_is_logged(caplog):
    class BrokenTriage(Services):
        def triage_understand(self, text):
            raise KeyError("confidence")

    s = BrokenTriage()
    g, c, _ = start_triage(s)
    authenticate(g, c)
    state = g.invoke(Command(resume={"text": "Me cobraron dos veces"}), c)
    assert state["reason"] == "triage_unavailable"
    ev = only_failure(caplog)
    assert ev["reason"] == "triage_unavailable" and ev["error"] == "KeyError"


def test_validator_node_outage_is_logged(caplog):
    services = LoginServices(); services.down = True
    graph, config, _ = start_validator(services)
    graph.invoke(Command(resume=GOOD), config)
    ev = only_failure(caplog)
    assert ev["reason"] == "validation_unavailable" and ev["detail"] == "MCP unavailable"


def test_disputes_graph_failure_is_logged(fake_services, caplog):
    services = fake_services()
    services.fail.add("create_handoff")
    graph, config, _ = start_disputes(services)
    state = resume(graph, config, "no")
    assert state["outcome"] == "service_unavailable"
    failures = events(caplog, "service.failure")
    assert failures and all(ev["reason"] == "tool_failure" for ev in failures)
    assert failures[-1]["node"] == "escalation"


@pytest.mark.parametrize("narrative, issue", [
    (None, "model_unavailable"),
    ("Se le reembolsarán 999 USD al cliente.", "promise"),
])
def test_narrative_fallback_is_logged(fake_services, caplog, narrative, issue):
    services = fake_services()
    services.narrative = narrative
    escalate_high_score(services)
    [ev] = events(caplog, "narrative.fallback")
    assert issue in ev["issues"]
