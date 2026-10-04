"""Clientes SINTÉTICOS para pruebas y demos. Nunca poner datos reales aquí."""
from datetime import date

from bank_agent.clients.identity import CustomerRecord, Product

DEMO_CUSTOMERS = {
    "1020304050": CustomerRecord("1020304050", date(1990, 4, 3), (
        Product("4111222233334444", "credit_card", "active"),
        Product("00987654321", "savings", "active"),
    )),
    "99887766": CustomerRecord("99887766", date(1985, 12, 1), (
        Product("5500111122223333", "debit_card", "active"),
    )),
    "55555555": CustomerRecord("55555555", None, ()),   # registro incompleto
}
