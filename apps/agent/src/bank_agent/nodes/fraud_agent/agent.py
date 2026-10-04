"""Agente de fraude (fraud path), 100% codigo, sin LLM.

Implementa el diagrama "3. Fraud path" de docs/STATE_MACHINE2.md:
  (bloqueo si falta) -> STATUS -> POLICY -> CONFIRM_DISPUTE ->
  ASK_MORE_CHARGES -> DSP-013 -> ESCALATION o INFORM

Por que no hay LLM aqui: en la tabla de estados del doc, cada paso de este
flujo esta marcado "Code" o "UI" en la columna LLM; ninguno pide al modelo
que decida ni que redacte texto libre. Las confirmaciones del cliente llegan
como booleanos de botones (regla global 6: "nunca texto libre interpretado").
Comparese con `card_emergency_agent`, que SI usa un LLM porque necesita
entender lenguaje libre ("me robaron la tarjeta").

La disputa no es solo de tarjetas: un cliente puede tener la transaccion en
cualquier producto (tarjeta, cuenta de ahorros, cuenta corriente). Por eso
"proteger el producto" antes de seguir con la disputa significa cosas
distintas segun el tipo:
- Tarjeta: se bloquea la tarjeta completa (`CardRepository.block_card`).
- Cuenta (savings/checking): NO se bloquea el producto entero, solo se
  suspende su capacidad de hacer transacciones
  (`AccountRepository.suspend_transactions`). El cliente sigue teniendo su
  cuenta, solo no puede operar con ella hasta que un humano la revise.

Fuera de alcance de este agente (lo resuelve el orquestador / otros agentes):
- SELECT_CARD / CONFIRM_BLOCK como emergencia de tarjeta perdida/robada:
  eso es el diagrama "2. Card emergency", implementado en
  `card_emergency_agent` (ese si es exclusivo de tarjetas: solo una tarjeta
  fisica se puede perder o robar). Este agente solo tiene su propio
  CONFIRM_BLOCK para la entrada directa desde ROUTE (diagrama 3), cuando el
  producto de la transaccion todavia no estaba protegido.
- FIND_TRANSACTION: encontrar la transaccion a partir del mensaje del cliente
  es un estado compartido con el path de "charge error"; este agente recibe
  `transaction_id` ya resuelto.
- BUILD_HANDOFF / WRITE_NARRATIVE / CREATE_TICKET: la redaccion del resumen
  para el empleado SI usa LLM (ver doc) y vive en el flujo de escalamiento,
  no en el agente de fraude. Este agente solo produce un `EscalationRequest`
  con cola, prioridad y motivo verificado.

Igual que `validator_agent/validator.py`: toda decision de a donde ir despues
la toma este codigo, nunca el texto del cliente ni un modelo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Callable, Optional

from bank_agent.clients.fraud_repository import (
    AccountRepository,
    CardRepository,
    DisputeRepository,
    RepositoryUnavailable,
    Transaction,
    TransactionRepository,
    TransactionStatus,
)
from bank_agent.config.settings import FraudPolicy, settings
from bank_agent.validator_agent.validator import IdentityValidator
from . import policy as policy_rules


class FraudState(str, Enum):
    CONFIRM_BLOCK = "CONFIRM_BLOCK"
    CONFIRM_DISPUTE = "CONFIRM_DISPUTE"
    ASK_MORE_CHARGES = "ASK_MORE_CHARGES"
    ESCALATED = "ESCALATED"
    DONE = "DONE"


@dataclass(frozen=True)
class EscalationRequest:
    queue: str      # "fraud" | "general"
    priority: str   # "P1" | "P2" | "P3"
    reason: str
    context: dict = field(default_factory=dict)


@dataclass
class FraudSession:
    session_id: str
    customer_id: str
    state: Optional[FraudState] = None
    selected_product: Optional[str] = None
    product_kind: Optional[str] = None            # "card" | "account"
    pending_transaction_id: Optional[str] = None
    protection_verified_at: Optional[datetime] = None
    disputed_transaction_ids: list = field(default_factory=list)
    denied_transaction_ids: list = field(default_factory=list)   # DSP-013
    charges_reviewed: int = 0
    max_fraud_score_seen: float = 0.0
    max_amount_usd_seen: float = 0.0
    escalation: Optional[EscalationRequest] = None


@dataclass
class FraudResult:
    state: FraudState
    next_step: str
    product: Optional[dict] = None   # {"product_number", "kind": "card"|"account", "status"}
    transaction: Optional[dict] = None
    case_id: Optional[str] = None
    rule_id: Optional[str] = None
    escalation: Optional[EscalationRequest] = None


class FraudAgent:
    """Una instancia compartida entre conversaciones (igual que IdentityValidator)."""

    def __init__(
        self,
        validator: IdentityValidator,
        cards: CardRepository,
        accounts: AccountRepository,
        transactions: TransactionRepository,
        disputes: DisputeRepository,
        policy: FraudPolicy = settings.fraud_policy,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        today: Callable[[], date] = date.today,
    ):
        self.validator = validator
        self.cards = cards
        self.accounts = accounts
        self.transactions = transactions
        self.disputes = disputes
        self.policy = policy
        self.clock = clock
        self.today = today
        self._sessions: dict[str, FraudSession] = {}

    # ---------- entrada ----------

    def evaluate_transaction(self, session_id: str, transaction_id: str) -> FraudResult:
        """Desde ROUTE (not_me / fraud_score alto), o desde card_emergency_agent
        tras FIND_TRANSACTION. Primera llamada del caso: crea la sesion si falta."""
        fs = self._get_or_create_session(session_id)
        tx = self.transactions.get_transaction(transaction_id)
        if tx is None or tx.customer_id != fs.customer_id or \
                not self.validator.can_access_product(session_id, tx.product_number):
            raise PermissionError("transaction not found or not owned by this session")

        fs.pending_transaction_id = transaction_id
        fs.charges_reviewed += 1
        fs.max_fraud_score_seen = max(fs.max_fraud_score_seen, tx.fraud_score)
        fs.max_amount_usd_seen = max(fs.max_amount_usd_seen, tx.amount_usd)

        # Producto aun sin proteger (entrada directa desde ROUTE, sin pasar por
        # card_emergency_agent). Si ya lo protegio ese agente (o una llamada
        # anterior), el repositorio compartido ya lo muestra protegido y este
        # paso se salta.
        kind, status = self._protection_lookup(tx.product_number)
        if not self._is_protected(kind, status):
            fs.selected_product = tx.product_number
            fs.product_kind = kind
            fs.state = FraudState.CONFIRM_BLOCK
            return FraudResult(state=fs.state, next_step="confirm_block",
                                product={"product_number": tx.product_number, "kind": kind, "status": status},
                                transaction=self._tx_dict(tx))

        return self._evaluate_status(fs, tx)

    def confirm_block(self, session_id: str, confirmed: bool) -> FraudResult:
        """Para tarjetas, bloquea el producto completo; para cuentas, solo
        suspende su capacidad de hacer transacciones (nunca el producto entero)."""
        fs = self._session(session_id)
        if not confirmed:
            return self._escalate(fs, "fraud", "P1", "protection_declined")

        if fs.product_kind == "card":
            new_status = self._retry_once(lambda: self.cards.block_card(fs.selected_product))
            expected = "blocked"
        else:
            new_status = self._retry_once(lambda: self.accounts.suspend_transactions(fs.selected_product))
            expected = "transactions_suspended"

        if new_status is None or new_status != expected:   # nunca reportar una proteccion sin verificar
            return self._escalate(fs, "general", "P2", "protection_not_verified")   # tool failure, fraud intent

        fs.protection_verified_at = self.clock()
        tx = self.transactions.get_transaction(fs.pending_transaction_id)
        return self._evaluate_status(fs, tx)

    def _protection_lookup(self, product_number: str) -> tuple[str, Optional[str]]:
        """Busca el producto primero como tarjeta, luego como cuenta.
        Devuelve (kind, status); kind es 'card' o 'account'."""
        status = self.cards.get_card_status(product_number)
        if status is not None:
            return "card", status
        status = self.accounts.get_account_status(product_number)
        if status is not None:
            return "account", status
        raise RepositoryUnavailable(f"product not found as card or account: {product_number}")

    @staticmethod
    def _is_protected(kind: str, status: Optional[str]) -> bool:
        return status == "blocked" if kind == "card" else status == "transactions_suspended"

    def _evaluate_status(self, fs: FraudSession, tx: Transaction) -> FraudResult:
        if tx.transaction_status == TransactionStatus.PENDING:
            return self._escalate(fs, "fraud", "P2", "pending_charge",
                                   context={"transaction_id": tx.transaction_id})

        if tx.transaction_status in (TransactionStatus.REVERSED, TransactionStatus.DECLINED):
            return self._ask_more(fs)

        # Approved -> POLICY
        existing_case = self.disputes.find_open_dispute(tx.transaction_id)
        decision = policy_rules.evaluate_approved_transaction(
            tx.transaction_date, self.today(), existing_case, self.policy,
        )
        if decision.outcome == "duplicate":
            return self._ask_more(fs, case_id=decision.case_id, rule_id=decision.rule_id)
        if decision.outcome == "outside_window":
            return self._escalate(fs, "fraud", "P2", "outside_window",
                                   context={"transaction_id": tx.transaction_id})

        fs.state = FraudState.CONFIRM_DISPUTE
        return FraudResult(state=fs.state, next_step="confirm_dispute",
                            transaction=self._tx_dict(tx), rule_id=decision.rule_id)

    def confirm_dispute(self, session_id: str, confirmed: bool) -> FraudResult:
        fs = self._session(session_id)
        transaction_id = fs.pending_transaction_id
        case_id = None
        if confirmed:
            case_id = self._retry_once(lambda: self.disputes.file_dispute(transaction_id, fs.customer_id))
            if case_id is None:   # FILE_AND_VERIFY: nunca reportar una disputa sin verificar
                return self._escalate(fs, "general", "P2", "dispute_not_verified",   # tool failure
                                       context={"transaction_id": transaction_id})
            fs.disputed_transaction_ids.append(transaction_id)
        else:
            fs.denied_transaction_ids.append(transaction_id)
        return self._ask_more(fs, case_id=case_id)

    def ask_more_charges(self, session_id: str, more: bool, transaction_id: Optional[str] = None) -> FraudResult:
        fs = self._session(session_id)
        if more:
            if not transaction_id:
                raise ValueError("transaction_id is required when more=True")
            return self.evaluate_transaction(session_id, transaction_id)
        return self._finalize(fs)

    # ---------- helpers de transicion ----------

    def _ask_more(self, fs: FraudSession, case_id: Optional[str] = None,
                  rule_id: Optional[str] = None) -> FraudResult:
        if fs.charges_reviewed >= self.policy.max_charges_per_case:
            return self._finalize(fs, case_id=case_id, rule_id=rule_id)
        fs.state = FraudState.ASK_MORE_CHARGES
        return FraudResult(state=fs.state, next_step="ask_more_charges",
                            case_id=case_id, rule_id=rule_id)

    def _finalize(self, fs: FraudSession, case_id: Optional[str] = None,
                  rule_id: Optional[str] = None) -> FraudResult:
        """DSP-013: cierre del caso de fraude o escalamiento."""
        if policy_rules.check_dsp013(fs.max_fraud_score_seen, fs.max_amount_usd_seen,
                                      len(fs.denied_transaction_ids), self.policy):
            priority = policy_rules.dsp013_priority(
                fs.max_fraud_score_seen, len(fs.denied_transaction_ids), self.policy,
            )
            return self._escalate(fs, "fraud", priority, "dsp_013", context={
                "disputed_transaction_ids": list(fs.disputed_transaction_ids),
                "denied_transaction_ids": list(fs.denied_transaction_ids),
            })
        fs.state = FraudState.DONE
        return FraudResult(state=fs.state, next_step="done", case_id=case_id, rule_id=rule_id)

    def _escalate(self, fs: FraudSession, queue: str, priority: str, reason: str,
                  context: Optional[dict] = None) -> FraudResult:
        req = EscalationRequest(queue=queue, priority=priority, reason=reason,
                                 context=context or {})
        fs.state = FraudState.ESCALATED
        fs.escalation = req
        return FraudResult(state=fs.state, next_step="escalate", escalation=req)

    @staticmethod
    def _retry_once(action: Callable[[], str]) -> Optional[str]:
        """Regla global 3: fallo de herramienta -> reintentar una vez, luego fallback seguro."""
        for _ in range(2):
            try:
                return action()
            except RepositoryUnavailable:
                continue
        return None

    def _get_or_create_session(self, session_id: str) -> FraudSession:
        self._require_auth(session_id)
        fs = self._sessions.get(session_id)
        if fs is None:
            v_session = self.validator.get_session(session_id)
            fs = FraudSession(session_id=session_id, customer_id=v_session.customer_id)
            self._sessions[session_id] = fs
        return fs

    def _session(self, session_id: str) -> FraudSession:
        self._require_auth(session_id)
        return self._sessions[session_id]

    def _require_auth(self, session_id: str) -> None:
        if not self.validator.is_authenticated(session_id):
            raise PermissionError("session is not authenticated")

    @staticmethod
    def _tx_dict(tx: Transaction) -> dict:
        return {
            "transaction_id": tx.transaction_id,
            "merchant_name": tx.merchant_name,
            "amount_usd": tx.amount_usd,
            "currency": tx.currency,
            "transaction_date": tx.transaction_date.isoformat(),
            "transaction_status": tx.transaction_status.value,
        }
