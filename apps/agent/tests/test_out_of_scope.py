"""Escenarios de OUT_OF_SCOPE (docs/state-machine.md, sección 1).

Cuando el clasificador dice "other", el agente dice qué puede hacer y ofrece las
intenciones como botones. Así un error del clasificador no deja al cliente atrapado:
la meta de la evaluación del Triage es 0 cargos que terminan "fuera de alcance".
Usa el mismo motor que test_scenarios_charge.py.
"""
import pytest

from test_scenarios_charge import Scenario, ScenarioServices, run_scenario

OOS = "out_of_scope"

SCENARIOS = [
    Scenario(
        "oos_close",
        "¿Cuál es el horario de las oficinas?", "other",
        steps=[(OOS, "close")],
        expect={"outcome": "out_of_scope", "intent": "other"},
        calls_absent=("find_transactions", "list_cards", "block_card"),
    ),
    Scenario(
        "oos_human",
        "Quiero abrir una cuenta de ahorros", "other",
        steps=[(OOS, "human")],
        expect={"outcome": "escalated", "reason": "requested_human", "queue": "general", "priority": "P3"},
        calls_absent=("find_transactions",),
    ),
    # El clasificador se equivocó y el cliente lo corrige con un botón.
    Scenario(
        "oos_customer_corrects_to_not_me",
        "Me sacaron plata de la cuenta", "other",
        steps=[(OOS, "not_me"), ("confirm_block", "yes"), ("confirm_dispute", "yes"), ("more_charges", "no")],
        expect={"outcome": "fraud_intake_complete", "intent": "not_me", "policy_rule": "DSP-100"},
    ),
    Scenario(
        "oos_customer_corrects_to_charge_error",
        "Tengo un tema con un cobro", "other", tx={"status": "Reversed"},
        steps=[(OOS, "charge_error"), ("explanation", "understood")],
        expect={"outcome": "explained", "intent": "charge_error", "explanation_rule": "EXP-003"},
        calls_absent=("block_card",),
    ),
    Scenario(
        "oos_customer_corrects_to_emergency",
        "No encuentro la billetera", "other",
        steps=[(OOS, "emergency"), ("confirm_block", "yes"), ("unrecognized_charge", "no")],
        expect={"outcome": "card_blocked", "intent": "emergency"},
        calls_absent=("find_transactions",),
    ),
]


@pytest.mark.parametrize("language", ["es", "pt"])
@pytest.mark.parametrize("sc", SCENARIOS, ids=lambda sc: sc.id)
def test_scenario(sc, language):
    services, state = run_scenario(sc, language)
    for key, expected in sc.expect.items():
        assert state.get(key) == expected, f"{sc.id}: {key}={state.get(key)!r}, esperado {expected!r}"
    for name in sc.calls_absent:
        assert name not in services.calls, f"{sc.id}: no debía llamar {name}"
    assert state["language"] == language


def test_out_of_scope_offers_the_intents_and_a_human():
    from langgraph.checkpoint.memory import InMemorySaver

    from bank_agent.graphs.disputes import build_graph
    from bank_agent.graphs.state import initial_state

    graph = build_graph(ScenarioServices(intent="other"), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "oos"}, "recursion_limit": 100}
    pause = graph.invoke(initial_state("oos", "trusted-session", "Hola"), config)["__interrupt__"][0].value
    assert pause["kind"] == OOS
    assert pause["options"] == ["not_me", "charge_error", "emergency", "close", "human"]
    assert "other" not in pause["options"]   # volver a "other" haría un ciclo