"""Chat interactivo para probar la cadena Agente 1 -> Agente 2 (card emergency)
-> Agente 3 (fraude), escribiendo como usuario.

Uso:
  python scripts/chat_fraud_demo.py            # datos de prueba sintéticos
  python scripts/chat_fraud_demo.py --debug    # muestra next_step/estado en cada turno

Necesita GROQ_API_KEY en un .env en la raíz del repo (Agente 1 y Agente 2
conversan con un LLM; Agente 3 es 100% código, sin LLM).

Flujo:
  1) Validación de identidad (Agente 1, igual que scripts/chat_validator.py).
  2) Elegís si querés reportar una emergencia de tarjeta (Agente 2, LLM) o ir
     directo a disputar un cargo puntual (Agente 3, sin pasar por el 2).
  3) Agente 2 conversa en lenguaje libre. Si reconocés un cargo, el script te
     deja elegir una transacción de la demo (simula FIND_TRANSACTION, que
     todavía no existe) y continúa con el Agente 3.
  4) Agente 3 no conversa: solo pregunta sí/no por cada paso fijo
     (CONFIRM_BLOCK, CONFIRM_DISPUTE, ASK_MORE_CHARGES).

Comandos: /salir en cualquier momento.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "agent" / "src"))

from dotenv import load_dotenv

load_dotenv()  # lee el .env de la raíz del repo si existe

from bank_agent.card_emergency_agent.agent import CardEmergencyAgent
from bank_agent.card_emergency_agent.service import CardEmergencyService
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
from bank_agent.fraud_agent.agent import FraudAgent
from bank_agent.validator_agent.agent import ValidationAgent
from bank_agent.validator_agent.validator import IdentityValidator

CARD_1 = "4111222233334444"
SAVINGS_1 = "00987654321"
CUSTOMER_ID = "1020304050"

DEMO_CUSTOMERS = {
    CUSTOMER_ID: CustomerRecord(CUSTOMER_ID, date(1990, 4, 3), (
        Product(CARD_1, "credit_card", "active"),
        Product(SAVINGS_1, "savings", "active"),
    )),
    "99887766": CustomerRecord("99887766", date(1985, 12, 1), (
        Product("5500111122223333", "debit_card", "active"),
    )),
}

DEMO_TRANSACTIONS = {
    "TX-100": Transaction("TX-100", CARD_1, CUSTOMER_ID, "Amazon", 45.0, "USD",
                           date(2026, 9, 28), TransactionStatus.APPROVED, fraud_score=10.0),
    "TX-200": Transaction("TX-200", CARD_1, CUSTOMER_ID, "Tienda Desconocida XYZ", 950.0, "USD",
                           date(2026, 9, 29), TransactionStatus.APPROVED, fraud_score=20.0),
    "TX-300": Transaction("TX-300", SAVINGS_1, CUSTOMER_ID, "Transferencia ACH", 300.0, "USD",
                           date(2026, 9, 30), TransactionStatus.APPROVED, fraud_score=15.0),
}


def yes_no(prompt: str) -> bool:
    while True:
        try:
            ans = input(f"{prompt} (sí/no): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if ans in ("/salir",):
            sys.exit(0)
        if ans in ("si", "sí", "s", "yes", "y"):
            return True
        if ans in ("no", "n"):
            return False
        print("Respondé sí o no.")


def print_escalation(result):
    if result.escalation:
        print(">>> ESCALADO:", json.dumps({
            "cola": result.escalation.queue, "prioridad": result.escalation.priority,
            "motivo": result.escalation.reason, "contexto": result.escalation.context,
        }, indent=2, ensure_ascii=False), "\n")


def run_fraud_agent(fraud: FraudAgent, session_id: str, transaction_id: str, debug: bool):
    r = fraud.evaluate_transaction(session_id, transaction_id)

    while True:
        if debug:
            print(f"  [fraud next_step={r.next_step}]")

        if r.next_step == "confirm_block":
            kind = r.product["kind"]
            label = "bloquear la tarjeta" if kind == "card" else "suspender las transacciones de la cuenta"
            confirmed = yes_no(f"Agente 3: ¿Confirmás {label} {r.product['product_number']}?")
            r = fraud.confirm_block(session_id, confirmed)

        elif r.next_step == "confirm_dispute":
            tx = r.transaction
            print(f"Agente 3: cargo de {tx['merchant_name']} por {tx['amount_usd']} {tx['currency']} "
                  f"({tx['transaction_date']}, estado {tx['transaction_status']}).")
            confirmed = yes_no("¿Querés que presentemos una disputa por este cargo?")
            r = fraud.confirm_dispute(session_id, confirmed)

        elif r.next_step == "ask_more_charges":
            if r.case_id:
                rule_note = f" (regla {r.rule_id})" if r.rule_id else ""
                print(f"Agente 3: caso {r.case_id}{rule_note}.")
            more = yes_no("¿Hay otro cargo que no reconocés?")
            if more:
                tx_id = input("  ID de transacción (TX-100 / TX-200 / TX-300): ").strip()
                r = fraud.ask_more_charges(session_id, True, transaction_id=tx_id)
            else:
                r = fraud.ask_more_charges(session_id, False)

        elif r.next_step == "escalate":
            print_escalation(r)
            return

        elif r.next_step == "done":
            print("Agente 3: listo, caso cerrado sin necesidad de un humano.\n")
            return

        else:
            print(f"[fraud_agent next_step desconocido: {r.next_step}]")
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="mostrar next_step/estado por turno")
    args = ap.parse_args()

    customers_repo = InMemoryCustomerRepository(DEMO_CUSTOMERS)
    cards_repo = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "active")]})
    accounts_repo = InMemoryAccountRepository({CUSTOMER_ID: [Account(SAVINGS_1, "active")]})
    transactions_repo = InMemoryTransactionRepository(DEMO_TRANSACTIONS)
    disputes_repo = InMemoryDisputeRepository()

    validator = IdentityValidator(customers_repo)
    fraud = FraudAgent(validator, cards_repo, accounts_repo, transactions_repo, disputes_repo,
                        today=lambda: date(2026, 10, 1))

    print("Modo demo. Para validarte:")
    print(f"  ID {CUSTOMER_ID} | nacimiento 03/04/1990 | productos {CARD_1} o {SAVINGS_1}")
    print("Transacciones de prueba: TX-100 (Amazon, $45), TX-200 (desconocido, $950), "
          "TX-300 (ACH en la cuenta de ahorros, $300)\n")

    # ---------- Agente 1: validación ----------
    agent1 = ValidationAgent(validator)
    session_id = agent1.session.session_id
    print("-- Agente 1 (validación de identidad) --\n")
    while True:
        try:
            text = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not text:
            continue
        if text == "/salir":
            return
        try:
            r1 = agent1.chat(text)
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}\n")
            continue
        print(f"Agente 1: {r1['reply']}\n")
        if args.debug:
            print(f"  [status={r1['status']} next_step={r1['next_step']}]\n")
        if r1["next_step"] == "triage":
            break
        if r1["next_step"] == "handoff_human":
            print(">>> Transferido a un humano. Fin de la demo.")
            return

    # ---------- elegir camino ----------
    print("\nValidado. ¿Qué querés probar?")
    print("  1) Reportar pérdida/robo de tarjeta (Agente 2, conversación libre)")
    print("  2) Ir directo a disputar un cargo puntual (Agente 3, sin pasar por el 2)")
    choice = input("Elegí 1 o 2: ").strip()

    if choice == "2":
        tx_id = input("ID de transacción (TX-100 / TX-200 / TX-300): ").strip()
        print()
        run_fraud_agent(fraud, session_id, tx_id, args.debug)
        return

    # ---------- Agente 2: card emergency ----------
    service = CardEmergencyService(validator, cards_repo)
    agent2 = CardEmergencyAgent(service, session_id)
    print("\n-- Agente 2 (emergencia de tarjeta) --\n")
    while True:
        try:
            text = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not text:
            continue
        if text == "/salir":
            return
        try:
            r2 = agent2.chat(text)
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}\n")
            continue
        print(f"Agente 2: {r2['reply']}\n")
        if args.debug:
            print(f"  [state={r2['state']} next_step={r2['next_step']}]\n")

        if r2["next_step"] == "escalate":
            print_escalation(r2)
            return
        if r2["next_step"] == "find_transaction":
            print(">>> Agente 2 terminó. Simulá FIND_TRANSACTION eligiendo la transacción.")
            tx_id = input("ID de transacción (TX-100 / TX-200 / TX-300): ").strip()
            print()
            run_fraud_agent(fraud, session_id, tx_id, args.debug)
            return


if __name__ == "__main__":
    main()
