"""Tests del servicio de emergencia de tarjeta con datos SINTÉTICOS (sin LLM)."""
from datetime import date, datetime, timezone

import pytest

from bank_agent.card_emergency_agent.service import CardEmergencyService
from bank_agent.clients.fraud_repository import Card, InMemoryCardRepository
from bank_agent.clients.repository import CustomerRecord, InMemoryCustomerRepository, Product
from bank_agent.validator_agent.validator import IdentityValidator

CUSTOMER_ID = "1020304050"
CARD_1 = "4111222233334444"

CUSTOMERS = {
    CUSTOMER_ID: CustomerRecord(CUSTOMER_ID, date(1990, 4, 3), (
        Product(CARD_1, "credit_card", "active"),
    )),
}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def authenticated_session():
    """IdentityValidator con una sesión YA autenticada (agente 1 ya hizo su trabajo)."""
    validator = IdentityValidator(InMemoryCustomerRepository(CUSTOMERS), clock=Clock())
    session = validator.new_session()
    result = validator.verify(session.session_id, CUSTOMER_ID, "1990-04-03", CARD_1)
    assert result.status.value == "VERIFIED"
    return validator, session.session_id


def make_service(validator, cards=None):
    cards = cards or InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "active")]})
    return CardEmergencyService(validator, cards, clock=Clock())


def test_start_requires_authenticated_session():
    validator = IdentityValidator(InMemoryCustomerRepository(CUSTOMERS), clock=Clock())
    session = validator.new_session()   # nunca verificada
    service = make_service(validator)
    with pytest.raises(PermissionError):
        service.start(session.session_id)


def test_single_card_auto_selected_and_blocked(authenticated_session):
    validator, session_id = authenticated_session
    service = make_service(validator)

    r = service.start(session_id)
    assert r.next_step == "confirm_block"
    assert r.card["product_number"] == CARD_1

    r = service.confirm_block(session_id, True)
    assert r.next_step == "ask_charge"
    assert r.card["status"] == "blocked"


def test_customer_declines_block_escalates_p1_fraud(authenticated_session):
    validator, session_id = authenticated_session
    service = make_service(validator)
    service.start(session_id)

    r = service.confirm_block(session_id, False)
    assert r.next_step == "escalate"
    assert r.escalation.queue == "fraud"
    assert r.escalation.priority == "P1"
    assert r.escalation.reason == "block_declined"


def test_already_blocked_card_skips_confirm_block(authenticated_session):
    validator, session_id = authenticated_session
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    service = make_service(validator, cards=cards)

    r = service.start(session_id)
    assert r.next_step == "ask_charge"


def test_several_cards_asks_to_select(authenticated_session):
    validator, session_id = authenticated_session
    # autenticado solo con CARD_1, pero simulamos un cliente con 2 tarjetas autorizadas
    validator.get_session(session_id).authorized_products = (CARD_1, "5500999900001111")
    cards = InMemoryCardRepository({CUSTOMER_ID: [
        Card(CARD_1, "active"), Card("5500999900001111", "active"),
    ]})
    service = make_service(validator, cards=cards)

    r = service.start(session_id)
    assert r.next_step == "select_card"
    assert {c["product_number"] for c in r.cards} == {CARD_1, "5500999900001111"}

    r = service.select_card(session_id, CARD_1)
    assert r.next_step == "confirm_block"


def test_no_card_on_file_escalates(authenticated_session):
    validator, session_id = authenticated_session
    service = make_service(validator, cards=InMemoryCardRepository({CUSTOMER_ID: []}))

    r = service.start(session_id)
    assert r.next_step == "escalate"
    assert r.escalation.reason == "no_card_on_file"


def test_no_recognized_charge_after_block_escalates_card_replacement(authenticated_session):
    validator, session_id = authenticated_session
    service = make_service(validator)
    service.start(session_id)
    service.confirm_block(session_id, True)

    r = service.ask_charge(session_id, False)
    assert r.next_step == "escalate"
    assert r.escalation.queue == "cards" and r.escalation.priority == "P3"
    assert r.escalation.reason == "card_replacement"


def test_recognized_charge_hands_off_to_fraud_agent(authenticated_session):
    validator, session_id = authenticated_session
    service = make_service(validator)
    service.start(session_id)
    service.confirm_block(session_id, True)

    r = service.ask_charge(session_id, True)
    assert r.next_step == "find_transaction"


def test_block_failure_retries_once_then_escalates(authenticated_session):
    validator, session_id = authenticated_session
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "active")]}, block_fail_times=2)
    service = make_service(validator, cards=cards)
    service.start(session_id)

    r = service.confirm_block(session_id, True)
    assert r.next_step == "escalate"
    assert r.escalation.reason == "block_not_verified"


def test_block_failure_once_then_succeeds_on_retry(authenticated_session):
    validator, session_id = authenticated_session
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "active")]}, block_fail_times=1)
    service = make_service(validator, cards=cards)
    service.start(session_id)

    r = service.confirm_block(session_id, True)
    assert r.next_step == "ask_charge"   # el reintento unico funciono
