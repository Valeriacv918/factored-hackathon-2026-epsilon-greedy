"""Validador de identidad: lógica 100% DETERMINÍSTICA.

El LLM no decide si alguien está autenticado. Solo extrae los datos de la
conversación y llama a `verify()`. Las reglas viven aquí, en código:

1. Se necesitan los 3 factores: número de documento (cédula, CURP, DNI...) +
   fecha de nacimiento + número de producto. El servidor devuelve el customer_id
   interno, que es el que se guarda en la sesión para la trazabilidad.
2. El producto debe pertenecer a ESE cliente (un cliente puede tener varios;
   basta con uno). Tras validar, la sesión queda autorizada para TODOS sus
   productos, y los agentes siguientes solo pueden operar sobre esa lista.
3. Mensaje de error genérico: nunca decimos cuál dato falló
   (evita enumerar clientes o adivinar fechas).
4. Máximo N intentos → bloqueo temporal → transferencia a humano.
5. La sesión autenticada expira.
6. Si el servidor MCP falla → no autenticamos y se ofrece humano (fallo seguro).
7. Auditoría sin PII: guardamos hash del documento, nunca el documento ni la fecha.

La comparación de los 3 factores la hace el servidor MCP (`verify_identity`):
el agente nunca ve la fecha de nacimiento guardada. Si coincide, el servidor
devuelve un token de sesión firmado; los demás tools lo usan para saber quién
es el cliente. Los límites (intentos, bloqueo, vida de la sesión) también son
del servidor: cada respuesta trae `attempts_left`, `locked_until` o `expires_at`,
y aquí solo se usan esos valores, sin copias propias que puedan desincronizarse.
Esas horas son UTC reales: el reloj del validador debe ser real, nunca el reloj
de escenario (SCENARIO_NOW).
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Callable, Optional

from ...config.settings import ValidationPolicy, settings
from ...clients.contracts import ServiceFailure
from ...clients.identity import IdentityChecker


class Status(str, Enum):
    VERIFIED = "VERIFIED"
    MISSING_FIELDS = "MISSING_FIELDS"
    INVALID_FORMAT = "INVALID_FORMAT"
    FAILED = "FAILED"
    LOCKED = "LOCKED"
    ALREADY_VERIFIED = "ALREADY_VERIFIED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# Siguiente paso que el orquestador debe tomar (no lo decide el LLM)
NEXT_STEP = {
    Status.VERIFIED: "triage",
    Status.ALREADY_VERIFIED: "triage",
    Status.MISSING_FIELDS: "ask_user",
    Status.INVALID_FORMAT: "ask_user",
    Status.FAILED: "ask_user",
    Status.LOCKED: "handoff_human",
    Status.SERVICE_UNAVAILABLE: "handoff_human",
}


@dataclass
class Session:
    session_id: str
    language: Optional[str] = None
    failed_attempts: int = 0                 # en esta conversación; solo informativo (handoff)
    locked_until: Optional[datetime] = None  # del servidor
    authenticated: bool = False
    customer_id: Optional[str] = None
    authorized_products: tuple = ()          # números de producto permitidos
    authenticated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None    # del servidor: vence junto con el token
    session_token: Optional[str] = None      # firmado por el servidor MCP; nunca va al LLM
    audit: list = field(default_factory=list)


@dataclass
class VerificationResult:
    status: Status
    next_step: str
    missing_fields: list = field(default_factory=list)
    attempts_left: Optional[int] = None
    products_count: int = 0                   # cuántos, nunca cuáles

    def for_llm(self) -> dict:
        """Lo ÚNICO que ve el modelo. Sin datos personales."""
        return {
            "status": self.status.value,
            "next_step": self.next_step,
            "missing_fields": self.missing_fields,
            "attempts_left": self.attempts_left,
            "products_count": self.products_count,
        }


# ---------- Normalización ----------

def normalize_document(raw: Optional[str]) -> Optional[str]:
    """Quita espacios, puntos y guiones: "1.020.304.050" y "1020-304-050" son el mismo
    documento. El servidor aplica la misma normalización a la columna document_number."""
    if not raw:
        return None
    canonical = str(raw).strip().upper()
    if re.fullmatch(r"CLI-[A-Z0-9]{1,16}", canonical):
        return canonical
    s = re.sub(r"[\s.\-]", "", str(raw)).upper()
    return s if re.fullmatch(r"[A-Z0-9]{4,20}", s) else None


def normalize_product(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = re.sub(r"[\s\-]", "", str(raw)).upper()
    return s if re.fullmatch(r"[A-Z0-9]{4,30}", s) else None


_DOB_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")


def parse_dob(raw: Optional[str], today: Optional[date] = None) -> Optional[date]:
    """Acepta ISO (AAAA-MM-DD) y formato latino DD/MM/AAAA.
    Nunca MM/DD: en es/pt '03/04/1990' es 3 de abril."""
    if not raw:
        return None
    today = today or date.today()
    for fmt in _DOB_FORMATS:
        try:
            d = datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
        if date(1900, 1, 1) <= d <= today:
            return d
        return None
    return None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


# ---------- Validador ----------

class IdentityValidator:
    def __init__(
        self,
        identity: IdentityChecker,
        policy: ValidationPolicy = settings.policy,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.identity = identity
        self.policy = policy
        self.clock = clock
        self._sessions: dict[str, Session] = {}

    # --- sesiones ---
    def new_session(self) -> Session:
        s = Session(session_id=secrets.token_urlsafe(16))
        self._sessions[s.session_id] = s
        return s

    def get_session(self, session_id: str) -> Session:
        return self._sessions[session_id]

    def is_authenticated(self, session_id: str) -> bool:
        """Úsalo en CADA tool de los agentes 2-7 antes de leer datos."""
        s = self._sessions.get(session_id)
        if not s or not s.authenticated:
            return False
        if s.expires_at is None or self.clock() >= s.expires_at:
            self._log(s, "session_expired")
            s.authenticated = False
            s.customer_id = None
            s.authorized_products = ()
            s.session_token = None
            s.expires_at = None
            return False
        return True

    def can_access_product(self, session_id: str, product_number: str) -> bool:
        """Control de acceso en la capa de tools, no en el prompt."""
        if not self.is_authenticated(session_id):
            return False
        p = normalize_product(product_number)
        return p is not None and p in self._sessions[session_id].authorized_products

    # --- verificación ---
    def verify(self, session_id: str, document_number: Optional[str],
               date_of_birth: Optional[str], product_number: Optional[str]) -> VerificationResult:
        t0 = time.perf_counter()
        s = self._sessions[session_id]
        now = self.clock()

        if self.is_authenticated(session_id):
            return self._res(s, Status.ALREADY_VERIFIED, t0,
                             products_count=len(s.authorized_products))

        if s.locked_until and now < s.locked_until:
            return self._res(s, Status.LOCKED, t0)

        # 1) completitud
        missing = [n for n, v in (("document_number", document_number),
                                  ("date_of_birth", date_of_birth),
                                  ("product_number", product_number)) if not v]
        if missing:
            return self._res(s, Status.MISSING_FIELDS, t0, missing=missing)

        # 2) formato (no cuenta como intento fallido: es un error de tipeo)
        doc, dob, prod = normalize_document(document_number), parse_dob(date_of_birth, now.date()), normalize_product(product_number)
        bad = [n for n, v in (("document_number", doc), ("date_of_birth", dob), ("product_number", prod)) if v is None]
        if bad:
            return self._res(s, Status.INVALID_FORMAT, t0, missing=bad)

        # 3) verificación en el servidor (misma respuesta para "no existe" y "no coincide")
        try:
            verify = getattr(self.repo, "verify_customer", None)
            record = verify(cid, dob, prod) if verify is not None else self.repo.get_customer(cid)
        except RepositoryUnavailable:
            return self._res(s, Status.SERVICE_UNAVAILABLE, t0)

        if result.status == "locked":
            s.failed_attempts += 1
            s.locked_until = result.locked_until   # hasta entonces no se vuelve a consultar
            return self._res(s, Status.LOCKED, t0, id_hash=_hash(doc))
        if result.status != "verified":
            s.failed_attempts += 1
            return self._res(s, Status.FAILED, t0, id_hash=_hash(doc), attempts_left=result.attempts_left)

        s.authenticated = True
        s.authenticated_at = now
        s.expires_at = result.expires_at
        s.customer_id = result.customer_id        # interno: trazabilidad del cliente
        s.authorized_products = tuple(p.upper() for p in result.product_numbers)
        s.session_token = result.session_token
        s.failed_attempts = 0
        return self._res(s, Status.VERIFIED, t0, id_hash=_hash(doc),
                         products_count=len(s.authorized_products))

    # --- helpers ---
    def _res(self, s: Session, status: Status, t0: float, missing=None,
             attempts_left=None, products_count=0, id_hash=None) -> VerificationResult:
        self._log(s, "verify", status=status.value, id_hash=id_hash,
                  latency_ms=round((time.perf_counter() - t0) * 1000, 1))
        return VerificationResult(status, NEXT_STEP[status], missing or [],
                                  attempts_left, products_count)

    def _log(self, s: Session, event: str, **data):
        s.audit.append({"ts": self.clock().isoformat(), "event": event, **data})
