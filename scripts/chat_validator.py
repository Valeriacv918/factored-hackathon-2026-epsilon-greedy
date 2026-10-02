"""Chat interactivo para probar el Agente 1 escribiendo como usuario.

Uso:
  python chat.py            # datos de prueba sintéticos (no necesita BigQuery)
  python chat.py --bq       # tu base real en BigQuery
  python chat.py --debug    # muestra estado, idioma y next_step en cada turno

Comandos dentro del chat:
  /nuevo   reinicia la conversación (nueva sesión)
  /estado  muestra el estado de la sesión
  /salir   termina
"""
import argparse
import json
from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "agent" / "src"))

from dotenv import load_dotenv

load_dotenv()  # lee el archivo .env si existe

from bank_agent.validator_agent.agent import ValidationAgent
from bank_agent.clients.repository import (CustomerRecord, InMemoryCustomerRepository, Product)
from bank_agent.validator_agent.validator import IdentityValidator

# Clientes SINTÉTICOS para probar sin BigQuery
DEMO_CUSTOMERS = {
    "1020304050": CustomerRecord("1020304050", date(1990, 4, 3), (
        Product("4111222233334444", "credit_card", "active"),
        Product("00987654321", "savings", "active"),
    )),
    "99887766": CustomerRecord("99887766", date(1985, 12, 1), (
        Product("5500111122223333", "debit_card", "active"),
    )),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bq", action="store_true", help="usar BigQuery real")
    ap.add_argument("--debug", action="store_true", help="mostrar detalles por turno")
    args = ap.parse_args()

    if args.bq:
        from bank_agent.clients.repository import BigQueryCustomerRepository
        repo = BigQueryCustomerRepository()
        print("Conectado a BigQuery.")
    else:
        repo = InMemoryCustomerRepository(DEMO_CUSTOMERS)
        print("Modo demo con clientes de prueba:")
        print("  ID 1020304050 | nacimiento 03/04/1990 | productos 4111222233334444 o 00987654321")
        print("  ID 99887766   | nacimiento 01/12/1985 | producto 5500111122223333")

    validator = IdentityValidator(repo)
    agent = ValidationAgent(validator)
    print("\nEscribe tu mensaje (/nuevo, /estado, /salir)\n")

    while True:
        try:
            text = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/salir":
            break
        if text == "/nuevo":
            agent = ValidationAgent(validator)
            print("-- nueva conversación --\n")
            continue
        if text == "/estado":
            s = agent.session
            print(json.dumps({
                "idioma": s.language, "autenticado": validator.is_authenticated(s.session_id),
                "intentos_fallidos": s.failed_attempts,
                "productos_autorizados": len(s.authorized_products),
                "bloqueado_hasta": s.locked_until.isoformat() if s.locked_until else None,
            }, indent=2, ensure_ascii=False), "\n")
            continue

        try:
            r = agent.chat(text)
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}\n")
            continue

        print(f"Agente: {r['reply']}\n")
        if args.debug:
            print(f"  [idioma={r['language']} ({r['language_confidence']}) "
                  f"estado={r['status']} next_step={r['next_step']}]\n")
        if r["next_step"] == "triage":
            print(">>> Validado. El Agente 1 terminó: este mensaje iría al Agente 2 (Triage),")
            print("    que aún no existe. Escribe /nuevo para probar otra vez o /salir.\n")
        if r["handoff"]:
            print(">>> Transferencia a humano. Paquete para el asesor:")
            print(json.dumps(r["handoff"], indent=2, ensure_ascii=False), "\n")


if __name__ == "__main__":
    main()