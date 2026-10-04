"""Tests del contrato del Triage."""
import pytest
from pydantic import ValidationError

from bank_agent.nodes.triage_agent.schemas import Intent, Route, Slots, TriageDecision, Understanding

def test_understanding_minimal():
    u = Understanding(intent=Intent.NOT_ME, confidence=0.9, wants_human=False)
    assert u.slots.merchant is None          # los datos vienen vacíos por defecto


def test_understanding_from_text_values():
    # Así llegará del LLM: texto, no objetos de Python
    u = Understanding.model_validate({
        "intent": "charge_error", "confidence": 0.8, "wants_human": True,
         "slots": {"merchant": "Amazon", "amount": "85"},
    })
    assert u.intent == Intent.CHARGE_ERROR and u.slots.amount == "85"


def test_invalid_intent_is_rejected():
    with pytest.raises(ValidationError):
        Understanding(intent="fraude", confidence=0.9, wants_human=False)


def test_confidence_must_be_between_0_and_1():
    with pytest.raises(ValidationError):
        Understanding(intent="other", confidence=1.5, wants_human=False)


def test_decision():
    d = TriageDecision(route=Route.CLARIFY_INTENT, intent=None, reason="low_confidence")
    assert d.route == "CLARIFY_INTENT"
