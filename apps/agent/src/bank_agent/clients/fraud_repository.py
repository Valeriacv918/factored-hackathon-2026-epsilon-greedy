"""Acceso a datos para el flujo de fraude: tarjetas, transacciones y disputas.

Misma separación que `repository.py`: el agente de fraude nunca consulta
BigQuery directamente. Protocolos + implementación en memoria para tests;
la implementación real contra `transactions`/`products`/`complaints`
(ver data/contracts/raw) se agrega cuando exista el servidor MCP.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Protocol

from .repository import RepositoryUnavailable

__all__ = [
    "TransactionStatus",
    "Card",
    "Account",
    "Transaction",
    "CardRepository",
    "AccountRepository",
    "TransactionRepository",
    "DisputeRepository",
    "RepositoryUnavailable",
    "InMemoryCardRepository",
    "InMemoryAccountRepository",
    "InMemoryTransactionRepository",
    "InMemoryDisputeRepository",
]


class TransactionStatus(str, Enum):
    APPROVED = "Approved"
    PENDING = "Pending"
    REVERSED = "Reversed"
    DECLINED = "Declined"


@dataclass(frozen=True)
class Card:
    product_number: str
    status: str   # "active" | "blocked"

    def masked(self) -> str:
        return "••••" + self.product_number[-4:]


@dataclass(frozen=True)
class Account:
    product_number: str
    status: str   # "active" | "transactions_suspended"


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    product_number: str
    customer_id: str
    merchant_name: str
    amount_usd: float
    currency: str
    transaction_date: date
    transaction_status: TransactionStatus
    fraud_score: float


class CardRepository(Protocol):
    def list_cards(self, customer_id: str) -> list[Card]: ...
    def block_card(self, product_number: str) -> str: ...            # devuelve el nuevo status
    def get_card_status(self, product_number: str) -> Optional[str]: ...


class AccountRepository(Protocol):
    """Cuentas (savings/checking): a diferencia de una tarjeta, no se bloquea
    el producto completo, solo se suspende su capacidad de hacer transacciones."""
    def get_account_status(self, product_number: str) -> Optional[str]: ...   # None si no es una cuenta
    def suspend_transactions(self, product_number: str) -> str: ...           # devuelve el nuevo status


class TransactionRepository(Protocol):
    def get_transaction(self, transaction_id: str) -> Optional[Transaction]: ...


class DisputeRepository(Protocol):
    def find_open_dispute(self, transaction_id: str) -> Optional[str]: ...   # DSP-004
    def file_dispute(self, transaction_id: str, customer_id: str) -> str: ...  # devuelve case_id


# ---------- Implementaciones en memoria (tests / demo) ----------

class InMemoryCardRepository:
    def __init__(self, cards_by_customer: dict[str, list[Card]], fail: bool = False,
                 block_fail_times: int = 0):
        self._cards = {cid: list(cs) for cid, cs in cards_by_customer.items()}
        self.fail = fail
        self.block_fail_times = block_fail_times   # simula fallas transitorias de block_card

    def list_cards(self, customer_id: str) -> list[Card]:
        if self.fail:
            raise RepositoryUnavailable("simulated outage")
        return list(self._cards.get(customer_id, []))

    def _find(self, product_number: str) -> Optional[tuple[str, int]]:
        for cid, cards in self._cards.items():
            for i, c in enumerate(cards):
                if c.product_number == product_number:
                    return cid, i
        return None

    def block_card(self, product_number: str) -> str:
        if self.fail or self.block_fail_times > 0:
            self.block_fail_times -= 1
            raise RepositoryUnavailable("simulated outage")
        loc = self._find(product_number)
        if loc is None:
            raise RepositoryUnavailable(f"card not found: {product_number}")
        cid, i = loc
        card = self._cards[cid][i]
        self._cards[cid][i] = Card(card.product_number, "blocked")
        return "blocked"

    def get_card_status(self, product_number: str) -> Optional[str]:
        if self.fail:
            raise RepositoryUnavailable("simulated outage")
        loc = self._find(product_number)
        if loc is None:
            return None
        cid, i = loc
        return self._cards[cid][i].status


class InMemoryAccountRepository:
    def __init__(self, accounts_by_customer: dict[str, list[Account]], fail: bool = False,
                 suspend_fail_times: int = 0):
        self._accounts = {cid: list(accs) for cid, accs in accounts_by_customer.items()}
        self.fail = fail
        self.suspend_fail_times = suspend_fail_times   # simula fallas transitorias de suspend_transactions

    def _find(self, product_number: str) -> Optional[tuple[str, int]]:
        for cid, accounts in self._accounts.items():
            for i, a in enumerate(accounts):
                if a.product_number == product_number:
                    return cid, i
        return None

    def get_account_status(self, product_number: str) -> Optional[str]:
        if self.fail:
            raise RepositoryUnavailable("simulated outage")
        loc = self._find(product_number)
        if loc is None:
            return None
        cid, i = loc
        return self._accounts[cid][i].status

    def suspend_transactions(self, product_number: str) -> str:
        if self.fail or self.suspend_fail_times > 0:
            self.suspend_fail_times -= 1
            raise RepositoryUnavailable("simulated outage")
        loc = self._find(product_number)
        if loc is None:
            raise RepositoryUnavailable(f"account not found: {product_number}")
        cid, i = loc
        account = self._accounts[cid][i]
        self._accounts[cid][i] = Account(account.product_number, "transactions_suspended")
        return "transactions_suspended"


class InMemoryTransactionRepository:
    def __init__(self, transactions: dict[str, Transaction], fail: bool = False):
        self._tx = dict(transactions)
        self.fail = fail

    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        if self.fail:
            raise RepositoryUnavailable("simulated outage")
        return self._tx.get(transaction_id)


class InMemoryDisputeRepository:
    def __init__(self, fail: bool = False, file_fail_times: int = 0):
        self._open: dict[str, str] = {}   # transaction_id -> case_id
        self._seq = 0
        self.fail = fail
        self.file_fail_times = file_fail_times   # simula fallas transitorias de file_dispute

    def find_open_dispute(self, transaction_id: str) -> Optional[str]:
        if self.fail:
            raise RepositoryUnavailable("simulated outage")
        return self._open.get(transaction_id)

    def file_dispute(self, transaction_id: str, customer_id: str) -> str:
        if self.fail or self.file_fail_times > 0:
            self.file_fail_times -= 1
            raise RepositoryUnavailable("simulated outage")
        existing = self._open.get(transaction_id)
        if existing:
            return existing
        self._seq += 1
        case_id = f"CASE-{self._seq:06d}"
        self._open[transaction_id] = case_id
        return case_id
