"""Tests del router del Triage (estado TRIAGE). No usan el LLM:
le pasamos a mano lo que "opinó" el LLM (Understanding) y revisamos la decisión."""
import pytest

from bank_agent.nodes.triage_agent.router import CONFIDENCE_THRESHOLD, decide
from bank_agent.nodes.triage_agent.schemas import Intent, Route, Understanding


def llm_says(intent, confidence=0.95, wants_human=False):
    """Atajo para fabricar lo que 'opinó' el LLM."""
    return Understanding(intent=intent, confidence=confidence, wants_human=wants_human)


# --- 1. Regla de emergencia: gana siempre ---
def test_emergency_keyword_wins_even_if_llm_says_other():
    d = decide("me robaron la tarjeta, ¿cuál es mi saldo?", llm_says(Intent.OTHER, 0.9))
    assert d.route == Route.EMERGENCY and d.reason == "emergency_keyword"


def test_emergency_keyword_wins_even_if_llm_failed():
    # El LLM falló (FALLBACK, confianza 0) pero la regla sigue protegiendo
    d = decide("roubaram meu cartão", llm_says(Intent.OTHER, 0.0))
    assert d.route == Route.EMERGENCY


def test_emergency_before_human():
    # Proteger el dinero primero: se bloquea la tarjeta y luego puede ir a un humano
    d = decide("me robaron la tarjeta, quiero hablar con un asesor", llm_says(Intent.EMERGENCY, 0.9, True))
    assert d.route == Route.EMERGENCY


# --- 2. Pedir humano ---
def test_human_by_keyword():
    d = decide("quiero hablar con una persona", llm_says(Intent.OTHER, 0.9))
    assert d.route == Route.ESCALATION and d.reason == "wants_human"


def test_human_by_llm():
    # Frase que las reglas no conocen, pero el LLM sí entendió
    d = decide("pásame con alguien de carne y hueso", llm_says(Intent.OTHER, 0.9, wants_human=True))
    assert d.route == Route.ESCALATION


def test_human_keeps_intent_for_priority():
    # Al escalar guardamos la intención: si es not_me, el ticket sube a P2
    d = decide("no reconozco un cargo, pásame un asesor", llm_says(Intent.NOT_ME, 0.9, True))
    assert d.route == Route.ESCALATION and d.intent == Intent.NOT_ME


# --- 3. Confianza baja: botones ---
def test_low_confidence_shows_buttons():
    d = decide("tengo un lío con la tarjeta", llm_says(Intent.OTHER, 0.3))
    assert d.route == Route.CLARIFY_INTENT and d.intent is None and d.reason == "low_confidence"


def test_llm_failure_shows_buttons():
    d = decide("mensaje cualquiera", llm_says(Intent.OTHER, 0.0))
    assert d.route == Route.CLARIFY_INTENT


def test_threshold_is_inclusive():
    # Exactamente en el umbral NO se pregunta
    d = decide("me cobraron doble", llm_says(Intent.CHARGE_ERROR, CONFIDENCE_THRESHOLD))
    assert d.route == Route.FIND_TRANSACTION


# --- 4. Intención del LLM ---
@pytest.mark.parametrize("intent,route", [
    (Intent.EMERGENCY, Route.EMERGENCY),
    (Intent.NOT_ME, Route.FIND_TRANSACTION),
    (Intent.CHARGE_ERROR, Route.FIND_TRANSACTION),
    (Intent.OTHER, Route.OUT_OF_SCOPE),
])
def test_route_by_llm_intent(intent, route):
    d = decide("texto sin palabras clave", llm_says(intent, 0.9))
    assert d.route == route and d.intent == intent and d.reason == "llm_intent"


# --- auditoría ---
def test_decision_keeps_llm_opinion():
    u = llm_says(Intent.OTHER, 0.9)
    d = decide("me robaron", u)
    assert d.understanding == u     # guardamos lo que opinó el LLM aunque no le hicimos caso
