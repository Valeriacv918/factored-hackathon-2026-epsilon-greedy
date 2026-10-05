"""Regression tests for the connected CLI flow and masked card presentation."""
import importlib.util
from pathlib import Path
from langgraph.types import Command
from test_card_emergency_test_graph import EmergencyServices, start, kind, YES, NO

spec = importlib.util.spec_from_file_location("disputes_cli", Path(__file__).resolve().parents[3] / "scripts/run_disputes.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_full_mode_connects_every_route():
    assert all(cli.flow_flags("full").values())
    assert not any(cli.flow_flags("validation-triage").values())


def test_emergency_remention_continues_through_fraud_to_end():
    s = EmergencyServices()
    g, c, _ = start(s, test_charge_error=True, test_fraud=True, test_escalation=True)
    g.invoke(Command(resume=YES), c)
    r = g.invoke(Command(resume=YES), c)
    assert kind(r) == "transaction_details"
    s.understand = lambda text, lang: {"intent": "emergency", "slots": {"amount": "20"}}
    r = g.invoke(Command(resume={"text": "Hay un cargo de 20 con la tarjeta robada"}), c)
    assert kind(r) == "select_transaction"
    r = g.invoke(Command(resume={"choice": "TX-1"}), c)
    assert kind(r) == "confirm_dispute"
    r = g.invoke(Command(resume=YES), c)
    assert kind(r) == "more_charges"
    r = g.invoke(Command(resume=NO), c)
    assert r["outcome"] == "fraud_intake_complete"
    assert s.actions.count("block_card") == 1 and r["case_ids"] == ["CASE-1"]


def test_human_request_during_search_creates_verified_handoff():
    s = EmergencyServices()
    g, c, _ = start(s, test_fraud=True, test_escalation=True)
    g.invoke(Command(resume=YES), c)
    g.invoke(Command(resume=YES), c)
    s.understand = lambda text, lang: {"wants_human": True, "slots": {}}
    r = g.invoke(Command(resume={"text": "Quiero un asesor"}), c)
    assert r["outcome"] == "escalated" and r["ticket_id"] == "TICKET-1"
    assert "read_notification" in s.actions


def test_card_choices_mask_ids_and_preserve_selection_with_duplicate_last4(monkeypatch, capsys):
    monkeypatch.setattr(cli, "read", lambda _: "2")
    question = dict(kind="select_card", message="Selecciona la tarjeta.",
                    options=["PRD-SECRET-A", "PRD-SECRET-B", "human"],
                    cards=[{"id": "PRD-SECRET-A", "last4": "1234"},
                           {"id": "PRD-SECRET-B", "last4": "1234"}])
    result = cli.answer(question)
    output = capsys.readouterr().out
    assert "PRD-SECRET" not in output and output.count("•••• 1234") == 2
    assert result.resume == {"choice": "PRD-SECRET-B"}


def test_confirmation_masks_card_and_missing_last4_never_falls_back_to_id(monkeypatch, capsys):
    monkeypatch.setattr(cli, "read", lambda _: "1")
    cli.answer(dict(kind="confirm_block", message="¿Confirmas?", options=["yes", "no"],
                    card_id="PRD-SECRET", last4="1234"))
    output = capsys.readouterr().out
    assert "•••• 1234" in output and "PRD-SECRET" not in output
    assert cli.masked_card("5357088837") == "Tarjeta sin terminación disponible"
    assert cli.masked_card(None) == "Tarjeta sin terminación disponible"


def test_debug_does_not_print_blocked_product_ids(monkeypatch, capsys):
    class Graph:
        def invoke(self, *args):
            return {"response": "Listo", "outcome": "done", "blocked_cards": ["PRD-SECRET"]}
    monkeypatch.setattr(cli, "read", lambda _: "Hola")
    cli.conversation(Graph(), "dev", True)
    output = capsys.readouterr().out
    assert "PRD-SECRET" not in output and '"blocked_cards_count": 1' in output
