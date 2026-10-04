"""Contrato del Triage: qué entra, qué sale.

Dos estados de la máquina de estados (STATE_MACHINE.md):
- UNDERSTAND (LLM): lee el mensaje y devuelve un `Understanding`.
- TRIAGE (código): con eso decide la ruta y devuelve un `TriageDecision`.
"""
import datetime as dt
import re
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum

# Símbolos y códigos de moneda que se pueden quitar de un monto sin cambiar su valor.
CURRENCY_MARKS = re.compile(r"R\$|US\$|[$€]|\b(?:USD|COP|BRL|MXN|ARS|EUR|CLP|PEN)\b")

class Intent(str, Enum):
    """Las 4 intenciones que distingue el Triage."""
    EMERGENCY = "emergency"            # tarjeta perdida, robada, clonada, retenida
    NOT_ME = "not_me"                   # "yo no hice esta compra"
    CHARGE_ERROR = "charge_error"       # "sí la hice, pero el cobro está mal"
    OTHER = "other"                     # todo lo demás


class Slots(BaseModel):
    """Datos que el cliente mencionó. Todos opcionales: si no los dijo, None.

    Los nombres y formatos siguen el argumento `slots` de find_transactions en el MCP
    (contracts/mcp/find_transactions.json), como el extractor original de Efraín.
    La normalización ocurre aquí, al salir del LLM: un dato que no se puede normalizar
    se descarta (None) en vez de invalidar todo el resultado, para no perder la intención.
    """
    merchant: str | None = Field(None, description="Comercio mencionado, p. ej. 'Amazon', 'iFood'")
    amount: str | None = Field(None, description="Monto mencionado como texto decimal, p. ej. '87.50'")
    currency: str | None = Field(None, description="Moneda si la dijo, código ISO de 3 letras: COP, BRL, USD...")
    date: dt.date | None = Field(None, description="Fecha exacta del cargo, AAAA-MM-DD")
    date_from: dt.date | None = Field(None, description="Inicio de un rango de fechas, AAAA-MM-DD")
    date_to: dt.date | None = Field(None, description="Fin de un rango de fechas, AAAA-MM-DD")
    product_hint: str | None = Field(None, description="Producto mencionado: 'tarjeta de crédito', 'termina en 1234'")

    @field_validator("merchant", mode="before")
    @classmethod
    def _merchant(cls, v):
        if not isinstance(v, str) or not v.strip():
            return None
        return v.strip()[:100]


    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, v):
        """'329,60' → '329.60', '$ 40' → '40', 'R$ 1.234,56' → '1234.56', 87 → '87'.
        Solo se quitan símbolos y códigos de moneda. Si queda texto ('450 mil' = 450.000)
        o un signo menos, el monto se descarta: nunca se adivina."""
        if isinstance(v, bool) or v is None:
            return None
        if isinstance(v, (int, float)):
            v = str(v)
        if not isinstance(v, str):
            return None
        v = CURRENCY_MARKS.sub("", v.strip().upper()).replace(" ", "")
        if not re.fullmatch(r"[\d.,]+", v):         # quedó texto, signo menos u otro carácter
            return None
        if "," in v and "." in v:                   # el último separador es el decimal
            v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
        elif "," in v:
            v = v.replace(",", ".")
        return v if re.fullmatch(r"\d+(\.\d{1,2})?", v) and float(v) > 0 else None

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, v):
        if not isinstance(v, str):
            return None
        v = v.strip().upper()
        return v if re.fullmatch(r"[A-Z]{3}", v) else None

    @model_validator(mode="after")
    def _dates(self):
        """Un rango al revés (inicio después del fin) se descarta: el MCP lo rechazaría."""
        if self.date_from and self.date_to and self.date_from > self.date_to:
            self.date_from = self.date_to = None
        return self

class Understanding(BaseModel):
    """Salida de UNDERSTAND (lo produce el LLM)."""
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0, description="Qué tan seguro está el modelo, 0 a 1")
    wants_human: bool = Field(description="¿El cliente pidió hablar con una persona?")
    slots: Slots = Field(default_factory=Slots)

class Route(str, Enum):
    """A dónde sigue la conversación después del Triage."""
    ESCALATION = "ESCALATION"               # pidió humano
    EMERGENCY = "EMERGENCY"                 # bloquear tarjeta
    FIND_TRANSACTION = "FIND_TRANSACTION"   # not_me o charge_error: buscar el cargo
    OUT_OF_SCOPE = "OUT_OF_SCOPE"           # no es algo que atendamos
    CLARIFY_INTENT = "CLARIFY_INTENT"       # no estamos seguros: mostrar botones


class TriageDecision(BaseModel):
    """Salida de TRIAGE (la produce el código, nunca el LLM)."""
    route: Route
    intent: Intent | None          # None solo cuando hay que aclarar
    reason: str                    # qué regla decidió: "wants_human", "fraud_keyword", "low_confidence"...
    understanding: Understanding | None = None   # lo que entendió el LLM (para auditoría)