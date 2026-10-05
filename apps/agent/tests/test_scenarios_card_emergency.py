"""Escenarios de emergencia de tarjeta (docs/STATE_MACHINE2.md, sección 2).

SELECT_CARD → ¿ya bloqueada? → CONFIRM_BLOCK → BLOCK_AND_VERIFY → ASK_CHARGE.
Cada escenario recorre el grafo real con servicios falsos y revisa pausas, final y herramientas.
"""
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.state import initial_state
from conftest import FakeServices

YES, NO = {"choice": "yes"}, {"choice": "no"}
SECOND_CARD = {"id": "card-2", "customer_id": "customer-1", "last4": "5678", "status": "Active"}


def run(services, answers, message="perdí mi tarjeta"):
    graph = build_graph(services, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "e"}, "recursion_limit": 100}
    state, kinds = graph.invoke(initial_state("e", "trusted-session", message), config), []
    for answer in answers:
        kinds.append(state["__interrupt__"][0].value["kind"])
        state = graph.invoke(Command(resume=answer), config)
    return state, kinds


@pytest.mark.parametrize("language", ["es", "pt"])
def test_one_card_block_verified_then_replacement(language):
    s = FakeServices(intent="emergency", language=language)
    state, kinds = run(s, [YES, NO])
    assert kinds == ["confirm_block", "unrecognized_charge"]
    assert (state["reason"], state["queue"], state["priority"]) == ("card_replacement", "cards", "P3")
    assert state["blocked_cards"] == ["card-1"] and state["block_verified_at"]["card-1"]
    assert s.calls.index("block_card") < s.calls.index("read_block")      # BLOCK_AND_VERIFY


def test_lost_wallet_offers_to_block_the_other_cards_too():
    s = FakeServices(intent="emergency"); s.cards.append(dict(SECOND_CARD))
    state, kinds = run(s, [{"choice": "card-2"}, YES, YES, NO], message="perdí mi billetera")
    assert kinds == ["select_card", "confirm_block", "confirm_block", "unrecognized_charge"]
    assert state["blocked_cards"] == ["card-2", "card-1"] and s.calls.count("block_card") == 2
    assert set(state["block_verified_at"]) == {"card-1", "card-2"}


def test_declining_an_extra_card_continues_without_escalating():
    """Rechazar la tarjeta EXTRA es decisión del cliente, no señal de riesgo: no es block_declined P1."""
    s = FakeServices(intent="emergency"); s.cards.append(dict(SECOND_CARD))
    state, kinds = run(s, [{"choice": "card-2"}, YES, NO, NO])
    assert kinds == ["select_card", "confirm_block", "confirm_block", "unrecognized_charge"]
    assert state["blocked_cards"] == ["card-2"] and state["skipped_cards"] == ["card-1"]
    assert (state["reason"], state["priority"]) == ("card_replacement", "P3")


def test_extra_card_question_is_different_and_shows_last4():
    s = FakeServices(intent="emergency"); s.cards.append(dict(SECOND_CARD))
    graph = build_graph(s, checkpointer=InMemorySaver()); config = {"configurable": {"thread_id": "e"}}
    graph.invoke(initial_state("e", "trusted-session", "perdí mi billetera"), config)
    first = graph.invoke(Command(resume={"choice": "card-2"}), config)["__interrupt__"][0].value
    extra = graph.invoke(Command(resume=YES), config)["__interrupt__"][0].value
    assert first["card_id"] == "card-2" and first["last4"] == "5678" and "Confirmas" in first["message"]
    assert extra["card_id"] == "card-1" and extra["last4"] == "1234" and "También" in extra["message"]


def test_already_blocked_cards_are_not_offered_again():
    s = FakeServices(intent="emergency"); s.cards.append({**SECOND_CARD, "status": "Blocked"})
    state, kinds = run(s, [{"choice": "card-1"}, YES, NO])
    assert kinds == ["select_card", "confirm_block", "unrecognized_charge"]
    assert s.calls.count("block_card") == 1


def test_select_card_shows_only_last4_never_full_number():
    s = FakeServices(intent="emergency"); s.cards.append(dict(SECOND_CARD))
    graph = build_graph(s, checkpointer=InMemorySaver())
    pause = graph.invoke(initial_state("e", "trusted-session", "perdí mi tarjeta"),
                         {"configurable": {"thread_id": "e"}})["__interrupt__"][0].value
    assert pause["cards"] == [{"id": "card-1", "last4": "1234"}, {"id": "card-2", "last4": "5678"}]


def test_already_blocked_card_skips_confirmation_and_never_blocks_again():
    s = FakeServices(intent="emergency"); s.cards[0]["status"] = "Blocked"
    state, kinds = run(s, [NO])
    assert kinds == ["unrecognized_charge"] and "block_card" not in s.calls


def test_declined_block_is_fraud_p1_without_writes():
    s = FakeServices(intent="emergency")
    state, _ = run(s, [NO])
    assert (state["reason"], state["queue"], state["priority"]) == ("block_declined", "fraud", "P1")
    assert "block_card" not in s.calls and state["ticket_id"]


@pytest.mark.parametrize("status", ["Closed", "Suspended"])
def test_no_active_card_escalates_without_blocking(status):
    s = FakeServices(intent="emergency"); s.cards[0]["status"] = status
    state, kinds = run(s, [])
    assert kinds == [] and state["reason"] == "no_blockable_card" and "block_card" not in s.calls


def test_unrecognized_charge_goes_to_fraud_and_does_not_ask_to_block_again():
    s = FakeServices(intent="emergency")
    graph = build_graph(s, checkpointer=InMemorySaver()); config = {"configurable": {"thread_id": "e"}}
    graph.invoke(initial_state("e", "trusted-session", "perdí mi tarjeta"), config)
    graph.invoke(Command(resume=YES), config)                      # bloquear
    state = graph.invoke(Command(resume=YES), config)              # sí hay un cargo
    assert state["__interrupt__"][0].value["kind"] == "transaction_details"
    s.intent = "not_me"                                            # la aclaración describe el cargo
    state = graph.invoke(Command(resume={"text": "un cargo de 40 dólares"}), config)
    assert state["__interrupt__"][0].value["kind"] == "confirm_dispute"   # no vuelve a pedir bloqueo
    assert s.calls.count("block_card") == 1


def test_mentioning_the_theft_while_describing_the_charge_does_not_restart_the_emergency():
    """Bug: en la aclaración, "la tarjeta que me robaron" activaba otra vez la regla de emergencia
    y el cliente volvía a "¿hay algún cargo?"; el cargo que describió se perdía."""
    s = FakeServices(intent="emergency")
    graph = build_graph(s, checkpointer=InMemorySaver()); config = {"configurable": {"thread_id": "e"}}
    graph.invoke(initial_state("e", "trusted-session", "me robaron la tarjeta"), config)
    graph.invoke(Command(resume=YES), config)
    graph.invoke(Command(resume=YES), config)
    state = graph.invoke(Command(resume={"text": "el cargo que hicieron con la tarjeta que me robaron"}), config)
    assert state["__interrupt__"][0].value["kind"] == "confirm_dispute"
    assert s.calls.count("block_card") == 1