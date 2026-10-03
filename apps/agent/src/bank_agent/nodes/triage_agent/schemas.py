"""Contrato del Triage: qué entra, qué sale.

Dos estados de la máquina de estados (STATE_MACHINE.md):
- UNDERSTAND (LLM): lee el mensaje y devuelve un `Understanding`.
- TRIAGE (código): con eso decide la ruta y devuelve un `TriageDecision`.
"""
from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """Las 4 intenciones que distingue el Triage."""
    CARD_EMERGENCY = "card_emergency"   # tarjeta perdida, robada, clonada, retenida
    NOT_ME = "not_me"                   # "yo no hice esta compra"
    CHARGE_ERROR = "charge_error"       # "sí la hice, pero el cobro está mal"
    OTHER = "other"                     # todo lo demás


class Slots(BaseModel):
    # TODO: mismo nombre que tablas transacciones
    """Datos que el cliente mencionó. Todos opcionales: si no los dijo, None.
    Los nombres siguen las columnas de la tabla `transactions`, para que
    FIND_TRANSACTION pueda buscar con ellos."""
    merchant_name: str | None = Field(None, description="Comercio mencionado, p. ej. 'Amazon', 'iFood'")
    amount: float | None = Field(None, description="Monto mencionado, solo el número")
    currency: str | None = Field(None, description="Moneda si la dijo: COP, BRL, USD...")
    date_mentioned: str | None = Field(None, description="Fecha tal como la dijo: 'ayer', '3 de marzo'")
    product_hint: str | None = Field(None, description="Producto mencionado: 'tarjeta de crédito', 'termina en 1234'")


class Understanding(BaseModel):
    """Salida de UNDERSTAND (lo produce el LLM)."""
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0, description="Qué tan seguro está el modelo, 0 a 1")
    wants_human: bool = Field(description="¿El cliente pidió hablar con una persona?")
    slots: Slots = Field(default_factory=Slots)

class Route(str, Enum):
    """A dónde sigue la conversación después del Triage."""
    ESCALATION = "ESCALATION"               # pidió humano
    CARD_EMERGENCY = "CARD_EMERGENCY"       # bloquear tarjeta
    FIND_TRANSACTION = "FIND_TRANSACTION"   # not_me o charge_error: buscar el cargo
    OUT_OF_SCOPE = "OUT_OF_SCOPE"           # no es algo que atendamos
    CLARIFY_INTENT = "CLARIFY_INTENT"       # no estamos seguros: mostrar botones


class TriageDecision(BaseModel):
    """Salida de TRIAGE (la produce el código, nunca el LLM)."""
    route: Route
    intent: Intent | None          # None solo cuando hay que aclarar
    reason: str                    # qué regla decidió: "wants_human", "fraud_keyword", "low_confidence"...
    understanding: Understanding | None = None   # lo que entendió el LLM (para auditoría)