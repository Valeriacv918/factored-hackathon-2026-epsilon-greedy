"""Chat interactivo para probar la cadena Agente 1 -> Agente 2 (card emergency)
-> Agente 3 (fraude), escribiendo como usuario.

Uso:
  python scripts/chat_fraud_demo.py            # datos de prueba sintéticos
  python scripts/chat_fraud_demo.py --debug    # muestra next_step/estado en cada turno

Necesita GROQ_API_KEY en un .env en la raíz del repo (solo el Agente 1 conversa
con un LLM; los Agentes 2 y 3 son 100% código, sin LLM: todas sus confirmaciones
son botones sí/no, nunca texto libre interpretado).

Flujo:
  1) Validación de identidad (Agente 1, igual que scripts/chat_validator.py).
  2) Elegís si querés reportar una emergencia de tarjeta (Agente 2) o ir
     directo a disputar un cargo puntual (Agente 3, sin pasar por el 2).
  3) Agentes 2 y 3 preguntan sí/no por cada paso fijo (CONFIRM_BLOCK,
     ASK_CHARGE, CONFIRM_DISPUTE, ASK_MORE_CHARGES). Cuando el Agente 2
     reconoce un cargo, el script te deja elegir una transacción de la demo
     (simula FIND_TRANSACTION, que todavía no existe) y continúa con el
     Agente 3.

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
from bank_agent.nodes.card_emergency_agent import CardEmergencyService
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
from bank_agent.clients.identity import CustomerRecord, InMemoryIdentityChecker, Product
from bank_agent.nodes.fraud_agent import FraudAgent
from bank_agent.nodes.validator_agent.validator import IdentityValidator
from bank_agent.nodes.validator_agent.agent import ValidationAgent

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


def run_card_emergency(service: CardEmergencyService, session_id: str, debug: bool) -> "str | None":
    """Agente 2: 100% botones, sin LLM. Devuelve el transaction_id a seguir
    en el Agente 3 (simulando FIND_TRANSACTION), o None si no corresponde."""
    try:
        r = service.start(session_id)
    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}\n")
        return None

    while True:
        if debug:
            print(f"  [card_emergency next_step={r.next_step}]")

        try:
            if r.next_step == "select_card":
                print("Agente 2: tenés varias tarjetas:")
                for c in r.cards:
                    print(f"  - {c['product_number']} ({c['masked']})")
                product_number = input("  ¿Cuál es? (número completo): ").strip()
                r = service.select_card(session_id, product_number)

            elif r.next_step == "confirm_block":
                confirmed = yes_no(f"Agente 2: ¿Confirmás bloquear la tarjeta {r.card['product_number']}?")
                r = service.confirm_block(session_id, confirmed)

            elif r.next_step == "ask_charge":
                has_charge = yes_no("Agente 2: ¿Hay un cargo puntual que no reconocés?")
                r = service.ask_charge(session_id, has_charge)

            elif r.next_step == "escalate":
                print_escalation(r)
                return None

            elif r.next_step == "find_transaction":
                print(">>> Agente 2 terminó. Simulá FIND_TRANSACTION eligiendo la transacción.")
                return input("ID de transacción (TX-100 / TX-200 / TX-300): ").strip()

            else:
                print(f"[card_emergency next_step desconocido: {r.next_step}]")
                return None
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}\n")
            continue


def run_fraud_agent(fraud: FraudAgent, session_id: str, transaction_id: str, debug: bool):
    try:
        r = fraud.evaluate_transaction(session_id, transaction_id)
    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}\n")
        return

    while True:
        if debug:
            print(f"  [fraud next_step={r.next_step}]")

        try:
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
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}\n")
            continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="mostrar next_step/estado por turno")
    args = ap.parse_args()

    identity = InMemoryIdentityChecker(DEMO_CUSTOMERS)
    cards_repo = InMemoryCardRepository({CUSTOMER_ID: [Card(CARD_1, "active")]})
    accounts_repo = InMemoryAccountRepository({CUSTOMER_ID: [Account(SAVINGS_1, "active")]})
    transactions_repo = InMemoryTransactionRepository(DEMO_TRANSACTIONS)
    disputes_repo = InMemoryDisputeRepository()

    validator = IdentityValidator(identity)
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
    print("  1) Reportar pérdida/robo de tarjeta (Agente 2)")
    print("  2) Ir directo a disputar un cargo puntual (Agente 3, sin pasar por el 2)")
    choice = input("Elegí 1 o 2: ").strip()

    if choice == "2":
        tx_id = input("ID de transacción (TX-100 / TX-200 / TX-300): ").strip()
        print()
        run_fraud_agent(fraud, session_id, tx_id, args.debug)
        return

    # ---------- Agente 2: card emergency ----------
    service = CardEmergencyService(validator, cards_repo)
    print("\n-- Agente 2 (emergencia de tarjeta) --\n")
    tx_id = run_card_emergency(service, session_id, args.debug)
    if tx_id:
        print()
        run_fraud_agent(fraud, session_id, tx_id, args.debug)


if __name__ == "__main__":
    main()
