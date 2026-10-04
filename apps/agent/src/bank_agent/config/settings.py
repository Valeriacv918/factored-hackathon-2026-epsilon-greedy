"""Configuración del agente: políticas y modelo.

El agente no tiene configuración de BigQuery: todos los datos llegan por el
servidor MCP (apps/mcp-server), que tiene la suya.
"""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationPolicy:
    max_attempts: int = 3                 # intentos fallidos antes de bloquear
    lockout_minutes: int = 15             # duración del bloqueo
    session_ttl_minutes: int = 15         # vida de la sesión autenticada
    supported_languages: tuple = ("es", "pt")
    default_language: str = "es"
    min_lang_confidence: float = 0.60     # umbral de lingua
    min_chars_for_detection: int = 12     # textos más cortos no cambian el idioma


@dataclass(frozen=True)
class FraudPolicy:
    """Umbrales deterministicos del flujo de fraude (docs/STATE_MACHINE2.md, DSP-005/DSP-013)."""
    fraud_score_threshold: float = float(os.getenv("DSP_FRAUD_SCORE_THRESHOLD", "30"))
    high_amount_usd_threshold: float = float(os.getenv("DSP_HIGH_AMOUNT_USD", "500"))
    dispute_window_days: int = int(os.getenv("DSP_WINDOW_DAYS", "90"))
    max_charges_per_case: int = int(os.getenv("DSP_MAX_CHARGES_PER_CASE", "3"))   # ASK_MORE_CHARGES


@dataclass(frozen=True)
class Settings:
    policy: ValidationPolicy = field(default_factory=ValidationPolicy)
    fraud_policy: FraudPolicy = field(default_factory=FraudPolicy)
    llm_model: str = os.getenv("LLM_MODEL", "groq:openai/gpt-oss-120b")


settings = Settings()