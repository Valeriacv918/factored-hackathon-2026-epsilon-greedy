"""Tests de las reglas fijas y del baseline del Triage.
Los mensajes de aquí NO están en evals/cases/triage_messages.csv (para no contaminar la evaluación)."""
import pytest

from bank_agent.nodes.triage_agent.rules import (asks_for_human, baseline_understand, contains_any,
                                           is_emergency, normalize)
from bank_agent.nodes.triage_agent.schemas import Intent


# --- utilidades ---
def test_normalize_removes_accents_and_uppercase():
    assert normalize("Perdí mi CARTÃO") == "perdi mi cartao"


def test_contains_any_matches_whole_words_only():
    assert contains_any("me robo la cartera", ["robo"])
    assert not contains_any("compré un robot", ["robo"])     # 'robo' dentro de 'robot' no cuenta


# --- regla de seguridad: emergencia de tarjeta ---
@pytest.mark.parametrize("text", [
    "Me robaron la tarjeta en el bus",
    "perdí mi tarjeta débito",
    "creo que me clonaron la tarjeta",
    "Roubaram meu cartão",
    "perdi meu cartão de crédito",
    "acho que meu cartão foi clonado",
])
def test_card_emergency_detected(text):
    assert is_emergency(text)


@pytest.mark.parametrize("text",

                         [
    "me cobraron dos veces",
    "quiero saber mi saldo",
    "não reconheço essa compra",
])
def test_not_card_emergency(text):
    assert not is_emergency(text)


# --- regla de seguridad: pedir humano ---
@pytest.mark.parametrize("text,expected", [
    ("necesito hablar con un asesor", True),
    ("quiero hablar con una persona", True),
    ("quero falar com um atendente", True),
    ("me cobraron doble", False),
])
def test_asks_for_human(text, expected):
    assert asks_for_human(text) is expected


# --- baseline ---
@pytest.mark.parametrize("text,intent", [
    ("me robaron la tarjeta", Intent.EMERGENCY),
    ("no reconozco ese cobro", Intent.NOT_ME),
    ("não fui eu que fiz essa compra", Intent.NOT_ME),
    ("me cobraron dos veces el almuerzo", Intent.CHARGE_ERROR),
    ("cadê meu estorno?", Intent.CHARGE_ERROR),
    ("cuál es mi saldo", Intent.OTHER),
])
def test_baseline_intent(text, intent):
    assert baseline_understand(text).intent == intent


def test_baseline_emergency_has_priority_over_not_me():
    # Si menciona robo Y compras que no hizo, gana la emergencia (regla global 1)
    assert baseline_understand("me robaron la tarjeta y hay compras que no hice").intent == Intent.EMERGENCY


def test_baseline_low_confidence_when_nothing_matches():
    assert baseline_understand("tengo una duda").confidence < 0.7
