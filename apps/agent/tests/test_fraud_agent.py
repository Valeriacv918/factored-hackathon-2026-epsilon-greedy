"""Tests del agente de fraude con datos SINTÉTICOS (sin BigQuery ni LLM)."""
from datetime import date, datetime, timezone

import pytest

from bank_agent.clients.fraud_repository import (
    Account,
    Card,
    InMemoryAccountRepository,
    InMemoryCardRepository,
    InMemoryDisputeRepository,
    InMemoryTransactionRepository,
    Transaction,
    TransactionStatus,
)
from bank_agent.clients.repository import CustomerRecord, InMemoryCustomerRepository, Product
from bank_agent.config.settings import FraudPolicy
from bank_agent.nodes.fraud_agent import FraudAgent
from bank_agent.validator_agent.validator import IdentityValidator

CUSTOMER_ID = "1020304050"
CARD_1 = "4111222233334444"
CARD_2 = "5500111122223333"
SAVINGS_1 = "00987654321"

CUSTOMERS = {
    CUSTOMER_ID: CustomerRecord(CUSTOMER_ID, date(1990, 4, 3), (
        Product(CARD_1, "credit_card", "active"),
        Product(SAVINGS_1, "savings", "active"),
    )),
    "99887766": CustomerRecord("99887766", date(1985, 12, 1), (
        Product(CARD_2, "debit_card", "active"),
    )),
}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def _tx(transaction_id, product_number=CARD_1, amount_usd=40.0, status=TransactionStatus.APPROVED,
        fraud_score=12.0, merchant="Netflix", tx_date=date(2026, 9, 20)):
    return Transaction(
        transaction_id=transaction_id, product_number=product_number, customer_id=CUSTOMER_ID,
        merchant_name=merchant, amount_usd=amount_usd, currency="USD",
        transaction_date=tx_date, transaction_status=status, fraud_score=fraud_score,
    )


@pytest.fixture
def authenticated_session():
    """IdentityValidator con una sesión YA autenticada (agente 1 ya hizo su trabajo)."""
    validator = IdentityValidator(InMemoryCustomerRepository(CUSTOMERS), clock=Clock())
    session = validator.new_session()
    result = validator.verify(session.session_id, CUSTOMER_ID, "1990-04-03", CARD_1)
    assert result.status.value == "VERIFIED"
    return validator, session.session_id


def make_fraud_agent(validator, cards=None, accounts=None, transactions=None, disputes=None, policy=None):
    cards = cards or InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "active")]})
    accounts = accounts or InMemoryAccountRepository({CUSTOMER_ID: [Account(SAVINGS_1, "active")]})
    transactions = transactions or InMemoryTransactionRepository({})
    disputes = disputes or InMemoryDisputeRepository()
    return FraudAgent(validator, cards, accounts, transactions, disputes,
                       policy=policy or FraudPolicy(), clock=Clock(),
                       today=lambda: date(2026, 10, 1))


# ---------- autorización ----------

def test_evaluate_transaction_requires_authenticated_session():
    validator = IdentityValidator(InMemoryCustomerRepository(CUSTOMERS), clock=Clock())
    session = validator.new_session()   # nunca verificada
    tx = _tx("TX-1")
    fraud = make_fraud_agent(validator, transactions=InMemoryTransactionRepository({"TX-1": tx}))
    with pytest.raises(PermissionError):
        fraud.evaluate_transaction(session.session_id, "TX-1")


def test_cannot_evaluate_a_transaction_from_another_customer(authenticated_session):
    validator, session_id = authenticated_session
    other_customer_tx = _tx("TX-OTHER", product_number=CARD_2)
    other_customer_tx = Transaction(**{**other_customer_tx.__dict__, "customer_id": "99887766"})
    fraud = make_fraud_agent(validator, transactions=InMemoryTransactionRepository({"TX-OTHER": other_customer_tx}))
    with pytest.raises(PermissionError):
        fraud.evaluate_transaction(session_id, "TX-OTHER")


# ---------- protección propia (entrada directa desde ROUTE, sin card_emergency) ----------

def test_card_not_protected_yet_asks_to_confirm_block(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1")
    fraud = make_fraud_agent(validator, transactions=InMemoryTransactionRepository({"TX-1": tx}))

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "confirm_block"
    assert r.product == {"product_number": CARD_1, "kind": "card", "status": "active"}


def test_customer_declines_protection_escalates_p1_fraud(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1")
    fraud = make_fraud_agent(validator, transactions=InMemoryTransactionRepository({"TX-1": tx}))
    fraud.evaluate_transaction(session_id, "TX-1")

    r = fraud.confirm_block(session_id, False)
    assert r.next_step == "escalate"
    assert r.escalation.queue == "fraud" and r.escalation.priority == "P1"
    assert r.escalation.reason == "protection_declined"


def test_card_already_blocked_skips_confirm_block(authenticated_session):
    """Si card_emergency_agent ya bloqueo la tarjeta, se ve en el repositorio compartido."""
    validator, session_id = authenticated_session
    tx = _tx("TX-1")
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "confirm_dispute"   # fue directo a STATUS/POLICY


# ---------- protección: cuentas (no tarjetas) ----------

def test_transaction_on_savings_account_suspends_transactions_not_the_product(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", product_number=SAVINGS_1)
    fraud = make_fraud_agent(validator, transactions=InMemoryTransactionRepository({"TX-1": tx}))

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "confirm_block"
    assert r.product == {"product_number": SAVINGS_1, "kind": "account", "status": "active"}

    r = fraud.confirm_block(session_id, True)
    assert r.next_step == "confirm_dispute"   # siguio a POLICY normalmente


def test_already_suspended_account_skips_confirm_block(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", product_number=SAVINGS_1)
    accounts = InMemoryAccountRepository({CUSTOMER_ID: [Account(SAVINGS_1, "transactions_suspended")]})
    fraud = make_fraud_agent(validator, accounts=accounts, transactions=InMemoryTransactionRepository({"TX-1": tx}))

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "confirm_dispute"


def test_account_suspend_failure_retries_once_then_escalates(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", product_number=SAVINGS_1)
    accounts = InMemoryAccountRepository({CUSTOMER_ID: [Account(SAVINGS_1, "active")]}, suspend_fail_times=2)
    fraud = make_fraud_agent(validator, accounts=accounts, transactions=InMemoryTransactionRepository({"TX-1": tx}))
    fraud.evaluate_transaction(session_id, "TX-1")

    r = fraud.confirm_block(session_id, True)
    assert r.next_step == "escalate"
    assert r.escalation.reason == "protection_not_verified"


# ---------- fraud path: estado de la transacción ----------

def test_pending_transaction_escalates_p2(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", status=TransactionStatus.PENDING)
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "escalate"
    assert r.escalation.queue == "fraud" and r.escalation.priority == "P2"
    assert r.escalation.reason == "pending_charge"


def test_reversed_transaction_needs_no_dispute(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", status=TransactionStatus.REVERSED)
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "ask_more_charges"   # nunca "confirm_dispute"


def test_approved_transaction_goes_to_confirm_dispute_and_files_case(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", status=TransactionStatus.APPROVED)
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "confirm_dispute"

    r = fraud.confirm_dispute(session_id, True)
    assert r.next_step == "ask_more_charges"
    assert r.case_id is not None

    r = fraud.ask_more_charges(session_id, False)
    assert r.next_step == "done"   # score y monto bajos -> no DSP-013


def test_duplicate_dispute_dsp004_reuses_case_id(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", status=TransactionStatus.APPROVED)
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    disputes = InMemoryDisputeRepository()
    existing_case = disputes.file_dispute("TX-1", CUSTOMER_ID)
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}),
                              disputes=disputes)

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "ask_more_charges"   # no se vuelve a pedir confirmación
    assert r.case_id == existing_case
    assert r.rule_id == "DSP-004"


def test_outside_window_dsp005_escalates(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", status=TransactionStatus.APPROVED, tx_date=date(2025, 1, 1))  # > 90 dias
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))

    r = fraud.evaluate_transaction(session_id, "TX-1")
    assert r.next_step == "escalate"
    assert r.escalation.reason == "outside_window"


# ---------- DSP-013 ----------

def test_high_fraud_score_triggers_dsp013_p1(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", status=TransactionStatus.APPROVED, fraud_score=85.0)
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))
    fraud.evaluate_transaction(session_id, "TX-1")
    fraud.confirm_dispute(session_id, True)

    r = fraud.ask_more_charges(session_id, False)
    assert r.next_step == "escalate"
    assert r.escalation.reason == "dsp_013" and r.escalation.priority == "P1"


def test_two_denied_charges_trigger_dsp013(authenticated_session):
    validator, session_id = authenticated_session
    tx1 = _tx("TX-1", status=TransactionStatus.APPROVED)
    tx2 = _tx("TX-2", status=TransactionStatus.APPROVED)
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    fraud = make_fraud_agent(validator, cards=cards,
                              transactions=InMemoryTransactionRepository({"TX-1": tx1, "TX-2": tx2}))

    fraud.evaluate_transaction(session_id, "TX-1")
    fraud.confirm_dispute(session_id, False)   # denied #1
    fraud.ask_more_charges(session_id, True, transaction_id="TX-2")
    fraud.confirm_dispute(session_id, False)   # denied #2

    r = fraud.ask_more_charges(session_id, False)
    assert r.next_step == "escalate"
    assert r.escalation.reason == "dsp_013" and r.escalation.priority == "P1"


def test_high_amount_triggers_dsp013_p2_only(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1", status=TransactionStatus.APPROVED, amount_usd=900.0, fraud_score=5.0)
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "blocked")]})
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))
    fraud.evaluate_transaction(session_id, "TX-1")
    fraud.confirm_dispute(session_id, True)

    r = fraud.ask_more_charges(session_id, False)
    assert r.next_step == "escalate"
    assert r.escalation.priority == "P2"   # solo monto alto, no score ni 2 negados


# ---------- fallo de herramienta (regla global 3) ----------

def test_block_failure_retries_once_then_escalates(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1")
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "active")]}, block_fail_times=2)
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))
    fraud.evaluate_transaction(session_id, "TX-1")

    r = fraud.confirm_block(session_id, True)
    assert r.next_step == "escalate"
    assert r.escalation.reason == "protection_not_verified"


def test_block_failure_once_then_succeeds_on_retry(authenticated_session):
    validator, session_id = authenticated_session
    tx = _tx("TX-1")
    cards = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "active")]}, block_fail_times=1)
    fraud = make_fraud_agent(validator, cards=cards, transactions=InMemoryTransactionRepository({"TX-1": tx}))
    fraud.evaluate_transaction(session_id, "TX-1")

    r = fraud.confirm_block(session_id, True)
    assert r.next_step == "confirm_dispute"   # el reintento unico funciono y siguio a POLICY
