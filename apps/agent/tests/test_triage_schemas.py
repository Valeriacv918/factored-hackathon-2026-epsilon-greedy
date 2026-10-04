"""Tests del contrato del Triage."""
import pytest
import datetime as dt

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



@pytest.mark.parametrize("raw, expected", [
    ("329,60", "329.60"), ("$ 40", "40"), (40, "40"), (87.5, "87.5"),
    ("R$ 1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("USD 15", "15"),
    ("450 mil", None), ("-5", None), ("0", None), ("abc", None), (True, None),
])
def test_amount_is_normalized_or_dropped(raw, expected):
    assert Slots(amount=raw).amount == expected


@pytest.mark.parametrize("raw, expected", [(" usd ", "USD"), ("brl", "BRL"), ("dólares", None), ("US", None)])
def test_currency_is_iso_or_dropped(raw, expected):
    assert Slots(currency=raw).currency == expected


def test_bad_slot_does_not_lose_the_intent():
    """Un monto ilegible se descarta; la intención se conserva (no cae al FALLBACK)."""
    u = Understanding.model_validate({"intent": "not_me", "confidence": 0.9, "wants_human": False,
                                      "slots": {"amount": "450 mil", "merchant": "Rappi"}})
    assert u.intent == Intent.NOT_ME and u.slots.amount is None and u.slots.merchant == "Rappi"


def test_inverted_date_range_is_dropped():
    today = dt.date.today()
    slots = Slots(date_from=today, date_to=today - dt.timedelta(days=5))
    assert slots.date_from is None and slots.date_to is None


def test_valid_date_range_is_kept():
    today = dt.date.today()
    slots = Slots(date_from=today - dt.timedelta(days=5), date_to=today)
    assert (slots.date_from, slots.date_to) == (today - dt.timedelta(days=5), today)
