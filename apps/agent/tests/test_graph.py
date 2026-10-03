import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.policy import Policy, decide
from bank_agent.graphs.state import initial_state
from fakes import FakeServices


def start(services, **kwargs):
    graph = build_graph(services, checkpointer=InMemorySaver(), **kwargs)
    config = {"configurable": {"thread_id": "test"}, "recursion_limit": 100}
    state = graph.invoke(initial_state("test", "trusted-session", "Cargo / cobrança"), config)
    return graph, config, state


def resume(graph, config, choice):
    return graph.invoke(Command(resume={"choice": choice}), config)


@pytest.mark.parametrize("language", ["es", "pt"])
def test_normal_fraud_intake(language):
    services = FakeServices(language=language)
    graph, config, state = start(services)
    assert state["__interrupt__"][0].value["kind"] == "confirm_block"
    assert "block_card" not in services.calls
    state = resume(graph, config, "yes")
    assert state["__interrupt__"][0].value["kind"] == "confirm_dispute"
    state = resume(graph, config, "yes")
    state = resume(graph, config, "no")
    assert state["outcome"] == "fraud_intake_complete"
    assert len(state["case_ids"]) == 1
    assert state["block_verified_at"] and state["case_verified_at"]
    assert services.calls.index("validate_session") < services.calls.index("understand")


def test_invalid_session_never_understands_or_reads_data():
    services = FakeServices()
    services.valid = False
    _, _, state = start(services)
    assert state["outcome"] == "authentication_required"
    assert "understand" not in services.calls


def test_unknown_language_asks_before_authentication():
    services = FakeServices(language=None)
    services.valid = False
    graph, config, state = start(services)
    assert state["__interrupt__"][0].value["options"] == ["es", "pt"]
    state = resume(graph, config, "pt")
    assert state["response"].startswith("Entre")
    assert "understand" not in services.calls


def test_unsupported_language_asks_es_or_pt():
    services = FakeServices(language="en")
    graph, config, state = start(services)
    assert state["__interrupt__"][0].value["options"] == ["es", "pt"]
    with pytest.raises(ValueError):
        resume(graph, config, "en")


def test_session_expires_during_confirmation():
    services = FakeServices()
    graph, config, _ = start(services)
    services.valid = False
    state = resume(graph, config, "yes")
    assert state["outcome"] == "authentication_required"
    assert "block_card" not in services.calls


def test_declined_block_escalates_without_blocking():
    services = FakeServices()
    graph, config, _ = start(services)
    state = resume(graph, config, "no")
    assert state["outcome"] == "escalated"
    assert (state["queue"], state["priority"]) == ("fraud", "P1")
    assert "block_card" not in services.calls
    assert state["handoff_at"]


@pytest.mark.parametrize("status", ["Pending", "Reversed", "Declined"])
@pytest.mark.parametrize("language", ["es", "pt"])
def test_charge_explanation_is_based_only_on_status(status, language):
    services = FakeServices(intent="charge_error", status=status, language=language)
    graph, config, state = start(services)
    assert state["__interrupt__"][0].value["kind"] == "explanation"
    state = resume(graph, config, "understood")
    assert state["outcome"] == "explained"
    assert "file_dispute" not in services.calls


def test_ambiguous_transaction_buttons():
    services = FakeServices(intent="charge_error")
    services.transactions.append({**services.transactions[0], "id": "tx-2"})
    graph, config, state = start(services)
    assert state["__interrupt__"][0].value["kind"] == "select_transaction"
    state = resume(graph, config, "tx-2")
    state = resume(graph, config, "yes")
    assert state["outcome"] == "dispute_filed"
    assert state["transaction"]["id"] == "tx-2"


def test_unowned_transaction_never_disclosed():
    services = FakeServices()
    services.transactions[0]["customer_id"] = "someone-else"
    _, _, state = start(services)
    assert state["outcome"] == "escalated"
    assert "transaction" not in state
    assert "block_card" not in services.calls


def test_timeout_after_commit_does_not_duplicate_dispute():
    services = FakeServices(intent="charge_error")
    services.timeout_after_write.add("file_dispute")
    graph, config, _ = start(services)
    state = resume(graph, config, "yes")
    assert state["outcome"] == "dispute_filed"
    assert len(services.records) == 1
    assert services.calls.count("file_dispute") == 2


def test_failed_ticket_does_not_report_success_or_loop():
    services = FakeServices()
    services.fail.add("create_handoff")
    graph, config, _ = start(services)
    state = resume(graph, config, "no")
    assert state["outcome"] == "service_unavailable"
    assert "handoff_at" not in state
    assert services.calls.count("create_handoff") == 2


def test_failed_verification_never_reports_a_case():
    services = FakeServices(intent="charge_error")
    services.fail.add("read_dispute")
    graph, config, _ = start(services)
    state = resume(graph, config, "yes")
    assert state["outcome"] == "escalated"
    assert state["case_ids"] == []


def test_high_fraud_score_reaches_p1():
    services = FakeServices(score="85")
    graph, config, _ = start(services)
    resume(graph, config, "yes")
    resume(graph, config, "yes")
    state = resume(graph, config, "no")
    assert state["reason"] == "DSP-013" and state["priority"] == "P1"


def test_lost_card_to_replacement():
    services = FakeServices(intent="card_emergency")
    graph, config, _ = start(services)
    resume(graph, config, "yes")
    state = resume(graph, config, "no")
    assert state["queue"] == "cards" and state["reason"] == "card_replacement"


def test_free_text_cannot_confirm_a_mutation():
    services = FakeServices()
    graph, config, _ = start(services)
    with pytest.raises(ValueError):
        graph.invoke(Command(resume="yes"), config)
    assert "block_card" not in services.calls


def test_human_can_be_requested_at_button_pause():
    services = FakeServices()
    graph, config, _ = start(services)
    state = resume(graph, config, "human")
    assert state["outcome"] == "escalated" and state["reason"] == "requested_human"


def test_turn_limit_escalates():
    _, _, state = start(FakeServices(), policy=Policy(max_turns=1))
    assert state["reason"] == "turn_limit"


def test_policy_boundary_and_missing_amount():
    services = FakeServices()
    tx = services.transactions[0]
    context = {"recent_dispute_count": 0}
    assert decide({**tx, "amount_usd": "500"}, context, services.now(), Policy())[0] == "file"
    assert decide({**tx, "amount_usd": "500.01"}, context, services.now(), Policy())[1] == "DSP-012"
    assert decide({**tx, "amount_usd": None}, context, services.now(), Policy())[0] == "escalate"


def test_two_charges_on_different_cards_each_require_block():
    services = FakeServices()
    graph, config, _ = start(services, policy=Policy(max_turns=20))
    resume(graph, config, "yes")
    resume(graph, config, "yes")
    state = resume(graph, config, "yes")
    assert state["__interrupt__"][0].value["kind"] == "transaction_details"
    services.cards.append({"id": "card-2", "customer_id": "customer-1", "last4": "5678", "status": "Active"})
    services.transactions = [{**services.transactions[0], "id": "tx-2", "card_id": "card-2"}]
    state = graph.invoke(Command(resume={"text": "Otro cargo de ayer"}), config)
    assert state["__interrupt__"][0].value["kind"] == "confirm_block"
    assert state["__interrupt__"][0].value["card_id"] == "card-2"
    resume(graph, config, "yes")
    resume(graph, config, "yes")
    state = resume(graph, config, "no")
    assert state["priority"] == "P1" and state["reason"] == "DSP-013"
    assert set(state["blocked_cards"]) == {"card-1", "card-2"}
    assert len(state["case_ids"]) == 2


def test_human_choice_cannot_bypass_language_and_security():
    services = FakeServices(language=None)
    graph, config, _ = start(services)
    with pytest.raises(ValueError):
        resume(graph, config, "human")
    assert "understand" not in services.calls
    assert "create_handoff" not in services.calls


def test_no_matches_exhausts_two_clarifications():
    services = FakeServices()
    services.transactions = []
    graph, config, _ = start(services)
    for _ in range(2):
        state = graph.invoke(Command(resume={"text": "Ayer, 40 USD"}), config)
    assert state["outcome"] == "escalated"
    assert state["reason"] == "transaction_unresolved"


def test_existing_case_never_creates_a_duplicate():
    services = FakeServices(intent="charge_error")
    services.existing = "existing-case"
    _, _, state = start(services)
    assert state["outcome"] == "existing_case"
    assert "existing-case" in state["response"]
    assert "file_dispute" not in services.calls


def test_fraud_without_card_escalates():
    services = FakeServices()
    services.transactions[0]["card_id"] = None
    _, _, state = start(services)
    assert state["reason"] == "no_blockable_card"
    assert state["outcome"] == "escalated"
