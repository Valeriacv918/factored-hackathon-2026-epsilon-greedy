import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent.graphs.state import initial_state
from bank_agent.graphs.validation_triage import build_graph
from bank_agent.nodes.triage_agent.schemas import Intent, Understanding
from test_fraud_test_graph import FraudServices
from test_validation_triage_graph import VALID_FORM

YES, NO = {"choice": "yes"}, {"choice": "no"}


class EmergencyServices(FraudServices):
    """Tarjeta CARD-1 activa; get_card refleja el bloqueo como lo hace el MCP (cards_effective)."""

    def __init__(self, card_status="Active"):
        super().__init__()
        self.understanding = Understanding(intent=Intent.EMERGENCY, confidence=.99, wants_human=False)
        self.card_status = card_status

    def tool(self, name, **kwargs):
        if name == "list_cards":
            self.actions.append(name)
            return {"cards": [{"id": "CARD-1", "customer_id": "CLI-ONE", "last4": "1234", "status": self.card_status}]}
        if name == "get_card":
            self.actions.append(name)
            return {"id": "CARD-1", "customer_id": "CLI-ONE", "last4": "1234", "status": self.card_status}
        result = super().tool(name, **kwargs)
        if name == "read_block" and result.get("verified"):
            self.card_status = "Blocked"
        return result


def start(s, message="Perdí mi tarjeta", **flags):
    g = build_graph(s, checkpointer=InMemorySaver(), test_card_emergency=True, **flags)
    c = {"configurable": {"thread_id": "one"}}
    g.invoke(initial_state("one", "", "Hola"), c)
    g.invoke(Command(resume=VALID_FORM), c)
    return g, c, g.invoke(Command(resume={"text": message}), c)


def kind(state):
    return state["__interrupt__"][0].value["kind"]


def test_lost_card_blocks_verifies_then_replacement_without_ticket():
    s = EmergencyServices(); g, c, r = start(s)
    assert kind(r) == "confirm_block" and "block_card" not in s.actions      # confirma antes de escribir
    r = g.invoke(Command(resume=YES), c)
    assert kind(r) == "unrecognized_charge" and r["blocked_cards"] == ["CARD-1"]
    assert s.actions.index("block_card") < s.actions.index("read_block")      # BLOCK_AND_VERIFY
    r = g.invoke(Command(resume=NO), c)
    assert (r["outcome"], r["reason"], r["queue"], r["priority"]) == ("human_required", "card_replacement", "cards", "P3")
    assert "create_handoff" not in s.actions


def test_declined_block_is_p1_and_never_writes():
    s = EmergencyServices(); g, c, _ = start(s)
    r = g.invoke(Command(resume=NO), c)
    assert (r["outcome"], r["reason"], r["queue"], r["priority"]) == ("human_required", "block_declined", "fraud", "P1")
    assert "block_card" not in s.actions


def test_already_blocked_card_skips_confirmation():
    s = EmergencyServices("Blocked"); g, c, r = start(s)
    assert kind(r) == "unrecognized_charge" and "block_card" not in s.actions


def test_no_active_card_reaches_human_without_writes():
    s = EmergencyServices("Closed"); g, c, r = start(s)
    assert (r["outcome"], r["reason"]) == ("human_required", "no_blockable_card") and "block_card" not in s.actions


def test_session_expired_at_confirmation_prevents_block():
    s = EmergencyServices(); g, c, _ = start(s); s.auth.clear()
    r = g.invoke(Command(resume=YES), c)
    assert r["outcome"] == "authentication_required" and "block_card" not in s.actions


def test_bad_block_receipt_never_reports_a_block():
    s = EmergencyServices(); s.fail_receipt = True; g, c, _ = start(s)
    r = g.invoke(Command(resume=YES), c)
    assert r["outcome"] == "service_unavailable" and not r.get("blocked_cards")


def test_unrecognized_charge_without_fraud_route_ends_ready_for_search():
    s = EmergencyServices(); g, c, _ = start(s)
    g.invoke(Command(resume=YES), c)
    r = g.invoke(Command(resume=YES), c)
    assert (r["outcome"], r["intent"]) == ("ready_for_transaction_search", "not_me")
    assert r["blocked_cards"] == ["CARD-1"]


def test_unrecognized_charge_continues_to_fraud_without_asking_to_block_again():
    s = EmergencyServices(); g, c, _ = start(s, test_fraud=True)
    g.invoke(Command(resume=YES), c)                                   # bloquear
    r = g.invoke(Command(resume=YES), c)                               # sí hay un cargo
    assert kind(r) == "transaction_details"
    r = g.invoke(Command(resume={"text": "un cargo del 10 de junio"}), c)
    r = g.invoke(Command(resume={"choice": "TX-1"}), c)
    assert kind(r) == "confirm_dispute" and s.actions.count("block_card") == 1


def test_replacement_with_escalation_creates_verified_sandbox_ticket():
    s = EmergencyServices(); g, c, _ = start(s, test_escalation=True)
    g.invoke(Command(resume=YES), c)
    r = g.invoke(Command(resume=NO), c)
    assert (r["outcome"], r["reason"], r["ticket_id"]) == ("escalated", "card_replacement", "TICKET-1")
    assert s.actions[-4:] == ["create_handoff", "read_handoff", "notify_employee", "read_notification"]
    assert s.handoff_packet["blocked_cards"] == ["CARD-1"] and s.handoff_packet["queue"] == "cards"


def test_without_the_flag_the_graph_still_stops_at_classification():
    s = EmergencyServices()
    g = build_graph(s, checkpointer=InMemorySaver())
    c = {"configurable": {"thread_id": "one"}}
    g.invoke(initial_state("one", "", "Hola"), c)
    g.invoke(Command(resume=VALID_FORM), c)
    r = g.invoke(Command(resume={"text": "Perdí mi tarjeta"}), c)
    assert r["outcome"] == "ready_for_card_emergency" and "list_cards" not in s.actions