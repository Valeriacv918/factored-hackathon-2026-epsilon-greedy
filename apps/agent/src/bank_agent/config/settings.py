"""Configuración del agente: políticas y modelo.

El agente no tiene configuración de BigQuery: todos los datos llegan por el
servidor MCP (apps/mcp-server), que tiene la suya.
"""
import os
from dataclasses import dataclass, field

from bank_agent.graphs.policy import Policy

# Single source for the dispute thresholds shared with the graph (graphs/policy.py).
_POLICY = Policy()


@dataclass(frozen=True)
class ValidationPolicy:
    # Intentos, bloqueo y vida de la sesión son del servidor MCP (IDENTITY_MAX_ATTEMPTS,
    # IDENTITY_LOCKOUT_MINUTES, SESSION_TTL_MINUTES): llegan en cada respuesta de
    # verify_identity, así que aquí no hay copia.
    supported_languages: tuple = ("es", "pt")
    default_language: str = "es"
    min_lang_confidence: float = 0.60     # umbral de lingua
    min_chars_for_detection: int = 12     # textos más cortos no cambian el idioma


@dataclass(frozen=True)
class FraudPolicy:
    """Umbrales deterministicos del flujo de fraude (docs/STATE_MACHINE2.md, DSP-005/DSP-013).

    Los valores salen de graphs/policy.Policy, que es la única fuente: así el
    agente de fraude y el grafo nunca aplican ventanas o umbrales distintos."""
    fraud_score_threshold: float = float(_POLICY.fraud_score)
    high_amount_usd_threshold: float = float(_POLICY.high_amount_usd)
    dispute_window_days: int = _POLICY.window_days
    max_charges_per_case: int = _POLICY.max_charges   # ASK_MORE_CHARGES


@dataclass(frozen=True)
class Settings:
    policy: ValidationPolicy = field(default_factory=ValidationPolicy)
    fraud_policy: FraudPolicy = field(default_factory=FraudPolicy)
    llm_model: str = os.getenv("LLM_MODEL", "groq:openai/gpt-oss-120b")


settings = Settings()