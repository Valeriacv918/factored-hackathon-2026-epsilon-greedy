"""Detección de idioma con lingua (determinística, sin LLM).

Decisiones:
- Solo comparamos entre los idiomas soportados (es, pt): reduce errores,
  sobre todo español vs portugués, que es la confusión más común.
- Textos cortos ("sí", "ok", "1234") no son confiables: no cambian el idioma
  que ya tenía la conversación ("idioma pegajoso").
- Si la confianza es baja, devolvemos `ambiguous=True` para que el agente
  pregunte en qué idioma prefiere seguir.
"""
from dataclasses import dataclass
from typing import Optional

from lingua import Language, LanguageDetectorBuilder

from ..config.settings import settings

_LANG_MAP = {Language.SPANISH: "es", Language.PORTUGUESE: "pt"}

_detector = (
    LanguageDetectorBuilder.from_languages(*_LANG_MAP.keys())
    .with_preloaded_language_models()
    .build()
)


@dataclass
class LanguageResult:
    language: str          # código ISO: es / pt
    confidence: float      # 0..1 según lingua
    ambiguous: bool        # True → conviene confirmar con el usuario
    source: str            # "detected" | "sticky" | "default"


def detect_language(text: str, previous: Optional[str] = None) -> LanguageResult:
    policy = settings.policy
    clean = (text or "").strip()
    letters = sum(ch.isalpha() for ch in clean)

    # Texto muy corto o casi sin letras → mantener idioma previo
    if letters < policy.min_chars_for_detection:
        if previous:
            return LanguageResult(previous, 1.0, False, "sticky")
        return LanguageResult(policy.default_language, 0.0, True, "default")

    values = _detector.compute_language_confidence_values(clean)
    best = values[0]
    lang = _LANG_MAP[best.language]
    conf = float(best.value)

    if conf < policy.min_lang_confidence:
        # Baja confianza: si ya había idioma, lo conservamos; si no, es ambiguo
        if previous:
            return LanguageResult(previous, conf, False, "sticky")
        return LanguageResult(lang, conf, True, "detected")

    return LanguageResult(lang, conf, False, "detected")
