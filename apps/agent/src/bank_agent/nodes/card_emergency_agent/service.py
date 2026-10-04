"""Servicio de emergencia de tarjeta (perdida/robo): 100% codigo, sin LLM.

Implementa el diagrama "2. Card emergency" de docs/STATE_MACHINE2.md:
SELECT_CARD -> CONFIRM_BLOCK -> BLOCK_AND_VERIFY -> ASK_CHARGE.

Las confirmaciones del cliente llegan como booleanos de botones, nunca como
texto libre interpretado por un modelo (misma regla global que `fraud_agent`).
Toda decisión de a dónde ir después la toma este código.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from bank_agent.clients.fraud_repository import CardRepository, RepositoryUnavailable
from bank_agent.nodes.validator_agent.validator import IdentityValidator


class EmergencyState(str, Enum):
    SELECT_CARD = "SELECT_CARD"
    CONFIRM_BLOCK = "CONFIRM_BLOCK"
    ASK_CHARGE = "ASK_CHARGE"
    ESCALATED = "ESCALATED"
    HANDED_OFF = "HANDED_OFF"   # ask_charge=True -> continua en fraud_agent.evaluate_transaction


@dataclass(frozen=True)
class EscalationRequest:
    queue: str      # "fraud" | "cards" | "general"
    priority: str   # "P1" | "P2" | "P3"
    reason: str
    context: dict = field(default_factory=dict)


@dataclass
class EmergencySession:
    session_id: str
    customer_id: str
    state: EmergencyState = EmergencyState.SELECT_CARD
    selected_card: Optional[str] = None
    block_verified_at: Optional[datetime] = None
    escalation: Optional[EscalationRequest] = None


@dataclass
class EmergencyResult:
    state: EmergencyState
    next_step: str   # "select_card" | "confirm_block" | "ask_charge" | "find_transaction" | "escalate"
    cards: list = field(default_factory=list)          # [{product_number, masked}] para SELECT_CARD
    card: Optional[dict] = None
    escalation: Optional[EscalationRequest] = None


class CardEmergencyService:
    """Un servicio compartido entre conversaciones (igual que IdentityValidator)."""

    def __init__(
        self,
        validator: IdentityValidator,
        cards: CardRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.validator = validator
        self.cards = cards
        self.clock = clock
        self._sessions: dict[str, EmergencySession] = {}

    def start(self, session_id: str) -> EmergencyResult:
        """Desde TRIAGE: card_emergency (p.ej. "me robaron la tarjeta")."""
        self._require_auth(session_id)
        v_session = self.validator.get_session(session_id)
        es = EmergencySession(session_id=session_id, customer_id=v_session.customer_id)
        self._sessions[session_id] = es

        cards = [
            c for c in self.cards.list_cards(es.customer_id)
            if self.validator.can_access_product(session_id, c.product_number)
        ]
        if not cards:
            return self._escalate(es, "general", "P3", "no_card_on_file")
        if len(cards) > 1:
            es.state = EmergencyState.SELECT_CARD
            return EmergencyResult(
                state=es.state, next_step="select_card",
                cards=[{"product_number": c.product_number, "masked": c.masked()} for c in cards],
            )
        es.selected_card = cards[0].product_number
        return self._after_card_selected(es)

    def select_card(self, session_id: str, product_number: str) -> EmergencyResult:
        es = self._session(session_id)
        if not self.validator.can_access_product(session_id, product_number):
            raise PermissionError("product not authorized for this session")
        es.selected_card = product_number
        return self._after_card_selected(es)

    def _after_card_selected(self, es: EmergencySession) -> EmergencyResult:
        status = self.cards.get_card_status(es.selected_card)
        if status == "blocked":
            es.state = EmergencyState.ASK_CHARGE
            return EmergencyResult(state=es.state, next_step="ask_charge",
                                    card={"product_number": es.selected_card, "status": status})
        es.state = EmergencyState.CONFIRM_BLOCK
        return EmergencyResult(state=es.state, next_step="confirm_block",
                                card={"product_number": es.selected_card, "status": status})

    def confirm_block(self, session_id: str, confirmed: bool) -> EmergencyResult:
        es = self._session(session_id)
        if not confirmed:
            return self._escalate(es, "fraud", "P1", "block_declined")

        new_status = self._retry_once(lambda: self.cards.block_card(es.selected_card))
        if new_status != "blocked":   # BLOCK_AND_VERIFY: nunca reportar sin verificar
            return self._escalate(es, "general", "P2", "block_not_verified")   # tool failure, fraud intent

        es.block_verified_at = self.clock()
        es.state = EmergencyState.ASK_CHARGE
        return EmergencyResult(state=es.state, next_step="ask_charge",
                                card={"product_number": es.selected_card, "status": new_status})

    def ask_charge(self, session_id: str, has_charge: bool) -> EmergencyResult:
        es = self._session(session_id)
        if not has_charge:
            # Emergencia de tarjeta sin cargo asociado: reemplazo, no es un caso de fraude.
            return self._escalate(es, "cards", "P3", "card_replacement")
        es.state = EmergencyState.HANDED_OFF
        return EmergencyResult(state=es.state, next_step="find_transaction")

    # ---------- helpers ----------

    def _escalate(self, es: EmergencySession, queue: str, priority: str, reason: str,
                  context: Optional[dict] = None) -> EmergencyResult:
        req = EscalationRequest(queue=queue, priority=priority, reason=reason, context=context or {})
        es.state = EmergencyState.ESCALATED
        es.escalation = req
        return EmergencyResult(state=es.state, next_step="escalate", escalation=req)

    @staticmethod
    def _retry_once(action: Callable[[], str]) -> Optional[str]:
        """Regla global 3: fallo de herramienta -> reintentar una vez, luego fallback seguro."""
        for _ in range(2):
            try:
                return action()
            except RepositoryUnavailable:
                continue
        return None

    def _session(self, session_id: str) -> EmergencySession:
        self._require_auth(session_id)
        return self._sessions[session_id]

    def _require_auth(self, session_id: str) -> None:
        if not self.validator.is_authenticated(session_id):
            raise PermissionError("session is not authenticated")
