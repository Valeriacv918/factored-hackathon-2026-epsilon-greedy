"""Escenarios del camino not_me / charge_error (docs/state-machine.md, secciones 1, 3 y 4).

Cada escenario es una conversación completa contra el grafo real, con servicios
sintéticos (sin red, MCP ni LLM): qué pausa ve el cliente, qué botón presiona y
dónde debe terminar. Se escribieron a partir del documento, antes de tocar el
código, y cubren los 5 casos demo más al menos un escenario por regla DSP y EXP.

Para agregar uno: copia un Scenario y cambia los datos de la transacción, los
pasos (kind de la pausa, botón) y el resultado esperado.
"""
from dataclasses import dataclass, field

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.state import initial_state
from conftest import FakeServices

TODAY_TX = "2026-09-30T12:00:00+00:00"   # FakeServices.now() es 2026-10-02
OLD_TX = "2026-06-01T12:00:00+00:00"     # 123 días antes: fuera de la ventana de 90 (DSP-005)


class ScenarioServices(FakeServices):
    """FakeServices con historial de disputas configurable (DSP-011)."""

    def __init__(self, *, recent_disputes=0, **kwargs):
        super().__init__(**kwargs)
        self.recent_disputes = recent_disputes

    def tool(self, name, *, session_ref, customer_id, arguments):
        if name == "dispute_context":
            assert self.validate_session(session_ref) == customer_id
            self.calls.append(name)
            return {"existing_case_id": self.existing, "recent_dispute_count": self.recent_disputes}
        return super().tool(name, session_ref=session_ref, customer_id=customer_id, arguments=arguments)


@dataclass
class Scenario:
    id: str
    message: str
    intent: str
    tx: dict = field(default_factory=dict)            # cambios sobre la transacción por defecto
    extra_txs: list = field(default_factory=list)     # más coincidencias (DSP-001)
    confidence: float = 0.99
    existing_case: str | None = None                  # DSP-004
    recent_disputes: int = 0                          # DSP-011
    steps: list = field(default_factory=list)         # [(kind de la pausa, botón)]
    expect: dict = field(default_factory=dict)        # campos del estado final
    calls_absent: tuple = ()                          # herramientas que NO deben llamarse


SCENARIOS = [
    # ---------------- Casos demo del documento ----------------
    Scenario(
        "demo_normal_not_me",
        "No reconozco una compra de 40 dólares", "not_me",
        steps=[("confirm_block", "yes"), ("confirm_dispute", "yes"), ("more_charges", "no")],
        expect={"outcome": "fraud_intake_complete", "policy_rule": "DSP-100"},
    ),
    Scenario(
        "demo_normal_alt_reversed",
        "Me cobraron algo que ya me habían devuelto", "charge_error", tx={"status": "Reversed"},
        steps=[("explanation", "understood")],
        expect={"outcome": "explained", "explanation_rule": "EXP-003"},
        calls_absent=("file_dispute", "block_card"),
    ),
    Scenario(
        "demo_ambiguous_three_matches",
        "Me cobraron mal en el supermercado", "charge_error",
        extra_txs=[{"id": "tx-2"}, {"id": "tx-3"}],
        steps=[("select_transaction", "tx-2"), ("confirm_dispute", "yes")],
        expect={"outcome": "dispute_filed", "policy_rule": "DSP-100"},
    ),
    Scenario(
        "demo_ambiguous_low_confidence",
        "Tengo un problema con un cobro", "charge_error", confidence=0.4, tx={"status": "Reversed"},
        steps=[("intent", "charge_error"), ("explanation", "understood")],
        expect={"outcome": "explained", "explanation_rule": "EXP-003", "intent": "charge_error"},
    ),
    Scenario(
        "demo_human_high_score",
        "No hice esta compra", "not_me", tx={"fraud_score": "85"},
        steps=[("confirm_block", "yes"), ("confirm_dispute", "yes"), ("more_charges", "no")],
        expect={"outcome": "escalated", "reason": "DSP-013", "queue": "fraud", "priority": "P1"},
    ),
    Scenario(
        "demo_human_block_declined",
        "No hice esta compra", "not_me",
        steps=[("confirm_block", "no")],
        expect={"outcome": "escalated", "reason": "block_declined", "queue": "fraud", "priority": "P1"},
        calls_absent=("block_card", "file_dispute"),
    ),

    # ---------------- ROUTE (DSP-010) ----------------
    Scenario(
        "dsp010_charge_error_with_high_score_goes_to_fraud",
        "Me cobraron de más", "charge_error", tx={"fraud_score": "45"},
        steps=[("confirm_block", "yes"), ("confirm_dispute", "yes"), ("more_charges", "no")],
        expect={"outcome": "escalated", "reason": "DSP-013", "priority": "P1"},
    ),

    # ---------------- Camino charge error (sección 4) ----------------
    Scenario(
        "exp002_pending_explained",
        "Tengo un cobro raro de un hotel", "charge_error", tx={"status": "Pending"},
        steps=[("explanation", "understood")],
        expect={"outcome": "explained", "explanation_rule": "EXP-002"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "exp006_declined_explained",
        "Me aparece un cobro que no pasó", "charge_error", tx={"status": "Declined"},
        steps=[("explanation", "understood")],
        expect={"outcome": "explained", "explanation_rule": "EXP-006"},
    ),
    Scenario(
        "explanation_rejected_escalates",
        "Sigue apareciendo el cobro", "charge_error", tx={"status": "Pending"},
        steps=[("explanation", "still_wrong")],
        expect={"outcome": "escalated", "reason": "explanation_rejected", "queue": "disputes",
                "priority": "P3", "explanation_rule": "EXP-002"},
    ),
    Scenario(
        "dsp100_charge_error_dispute_filed",
        "Me cobraron dos veces", "charge_error",
        steps=[("confirm_dispute", "yes")],
        expect={"outcome": "dispute_filed", "policy_rule": "DSP-100"},
        calls_absent=("block_card",),
    ),
    Scenario(
        "dsp100_charge_error_dispute_cancelled",
        "Me cobraron dos veces", "charge_error",
        steps=[("confirm_dispute", "no")],
        expect={"outcome": "cancelled"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "dsp004_charge_error_existing_case",
        "Me cobraron dos veces", "charge_error", existing_case="CASE-9",
        expect={"outcome": "existing_case", "policy_rule": "DSP-004"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "dsp005_charge_error_outside_window_denied",
        "Me cobraron mal en junio", "charge_error", tx={"date": OLD_TX},
        expect={"outcome": "outside_window", "policy_rule": "DSP-005"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "dsp011_repeat_disputes_escalates",
        "Me cobraron dos veces", "charge_error", recent_disputes=2,
        expect={"outcome": "escalated", "reason": "DSP-011", "queue": "disputes", "priority": "P3"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "dsp012_high_amount_escalates",
        "Me cobraron 600 dólares de más", "charge_error", tx={"amount": "600.00", "amount_usd": "600.00"},
        expect={"outcome": "escalated", "reason": "DSP-012", "queue": "disputes", "priority": "P3"},
        calls_absent=("file_dispute",),
    ),

    # ---------------- Camino de fraude (sección 3) ----------------
    Scenario(
        "fraud_pending_charge_escalates",
        "No hice esta compra", "not_me", tx={"status": "Pending"},
        steps=[("confirm_block", "yes")],
        expect={"outcome": "escalated", "reason": "pending_fraud", "queue": "fraud", "priority": "P2"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "fraud_reversed_blocks_without_dispute",
        "No hice esta compra", "not_me", tx={"status": "Reversed"},
        steps=[("confirm_block", "yes"), ("more_charges", "no")],
        expect={"outcome": "fraud_intake_complete"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "dsp004_fraud_existing_case_not_duplicated",
        "No hice esta compra", "not_me", existing_case="CASE-9",
        steps=[("confirm_block", "yes"), ("more_charges", "no")],
        expect={"outcome": "fraud_intake_complete", "policy_rule": "DSP-004"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "dsp005_fraud_outside_window_escalates",
        "No hice esta compra de junio", "not_me", tx={"date": OLD_TX},
        steps=[("confirm_block", "yes")],
        expect={"outcome": "escalated", "reason": "DSP-005", "queue": "fraud", "priority": "P2"},
        calls_absent=("file_dispute",),
    ),
    Scenario(
        "dsp013_amount_only_is_p2",
        "No hice esta compra de 600 dólares", "not_me", tx={"amount": "600.00", "amount_usd": "600.00"},
        steps=[("confirm_block", "yes"), ("confirm_dispute", "yes"), ("more_charges", "no")],
        expect={"outcome": "escalated", "reason": "DSP-013", "queue": "fraud", "priority": "P2"},
    ),
]


def run_scenario(sc: Scenario, language: str):
    services = ScenarioServices(language=language, intent=sc.intent, recent_disputes=sc.recent_disputes)
    services.confidence = sc.confidence
    services.existing = sc.existing_case
    services.transactions[0].update(sc.tx)
    services.transactions += [{**services.transactions[0], **extra} for extra in sc.extra_txs]

    graph = build_graph(services, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": sc.id}, "recursion_limit": 100}
    state = graph.invoke(initial_state(sc.id, "trusted-session", sc.message), config)
    seen = []
    for kind, choice in sc.steps:
        pause = state.get("__interrupt__")
        assert pause, f"{sc.id}: esperaba la pausa {kind!r}, pero la conversación terminó en {state.get('outcome')!r} (pausas: {seen})"
        assert pause[0].value["kind"] == kind, f"{sc.id}: esperaba {kind!r}, llegó {pause[0].value['kind']!r} (pausas: {seen})"
        seen.append(kind)
        state = graph.invoke(Command(resume={"choice": choice}), config)
    assert not state.get("__interrupt__"), f"{sc.id}: quedó una pausa sin responder: {state['__interrupt__'][0].value['kind']!r}"
    return services, state


@pytest.mark.parametrize("language", ["es", "pt"])
@pytest.mark.parametrize("sc", SCENARIOS, ids=lambda sc: sc.id)
def test_scenario(sc, language):
    services, state = run_scenario(sc, language)
    for key, expected in sc.expect.items():
        assert state.get(key) == expected, f"{sc.id}: {key}={state.get(key)!r}, esperado {expected!r}"
    for name in sc.calls_absent:
        assert name not in services.calls, f"{sc.id}: no debía llamar {name}"
    assert state["language"] == language
    if state["outcome"] == "escalated":   # toda escalación termina con ticket y hora de entrega
        assert state["ticket_id"] and state["handoff_at"]


def test_every_rule_has_a_scenario():
    """El documento pide al menos un escenario por regla DSP y EXP del camino."""
    covered = {v for sc in SCENARIOS for k, v in sc.expect.items() if k in {"policy_rule", "explanation_rule", "reason"}}
    covered |= {"DSP-001"} if any(sc.extra_txs for sc in SCENARIOS) else set()
    covered |= {"DSP-010"} if any(sc.id.startswith("dsp010") for sc in SCENARIOS) else set()
    required = {"DSP-001", "DSP-004", "DSP-005", "DSP-010", "DSP-011", "DSP-012", "DSP-013", "DSP-100",
                "EXP-002", "EXP-003", "EXP-006"}
    assert required <= covered, f"Faltan escenarios para: {sorted(required - covered)}"