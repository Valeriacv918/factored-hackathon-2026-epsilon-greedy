"""Detección de idioma con lingua (determinística, sin LLM).

Decisiones:
- Solo comparamos entre los idiomas soportados (es, pt): reduce errores,
  sobre todo español vs portugués, que es la confusión más común.
- Textos cortos ("sí", "ok", "1234") no son confiables: no cambian el idioma
  que ya tenía la conversación ("idioma pegajoso").
- Si la confianza es baja, devolvemos `ambiguous=True` para que el agente
  pregunte en qué idioma prefiere seguir (en ambos idiomas). Mientras tanto el
  idioma es el predeterminado: una suposición poco confiable no se guarda.
- Excepción al idioma pegajoso: si el texto corto nombra un idioma ("español",
  "português"), es la respuesta a esa pregunta y manda (source="choice").
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from lingua import Language, LanguageDetectorBuilder

from ...config.settings import settings

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
    source: str            # "detected" | "sticky" | "default" | "choice"


# Nombres de idioma (sin tildes) con los que el cliente responde "¿español o portugués?".
_CHOICES = {
    "espanol": "es", "castellano": "es", "espanhol": "es", "spanish": "es",
    "portugues": "pt", "portuguesa": "pt", "portuguese": "pt",
}


def explicit_choice(text: str) -> Optional[str]:
    """El idioma que el texto nombra, si nombra exactamente uno ("en español" → es)."""
    plain = unicodedata.normalize("NFKD", (text or "").lower())
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    words = re.findall(r"[a-z]+", plain)
    if words in (["es"], ["pt"]):
        return words[0]
    named = {_CHOICES[w] for w in words if w in _CHOICES}
    return named.pop() if len(named) == 1 else None


def detect_language(text: str, previous: Optional[str] = None) -> LanguageResult:
    policy = settings.policy
    clean = (text or "").strip()
    letters = sum(ch.isalpha() for ch in clean)

    # Texto muy corto o casi sin letras → mantener idioma previo, salvo que elija uno
    if letters < policy.min_chars_for_detection:
        if choice := explicit_choice(clean):
            return LanguageResult(choice, 1.0, False, "choice")
        if previous:
            return LanguageResult(previous, 1.0, False, "sticky")
        return LanguageResult(policy.default_language, 0.0, True, "default")

    values = _detector.compute_language_confidence_values(clean)
    best = values[0]
    lang = _LANG_MAP[best.language]
    conf = float(best.value)

    if conf < policy.min_lang_confidence:
        # Baja confianza: si ya había idioma, lo conservamos; si no, es ambiguo y
        # usamos el predeterminado (la suposición de lingua no es confiable)
        if previous:
            return LanguageResult(previous, conf, False, "sticky")
        return LanguageResult(policy.default_language, conf, True, "default")

    return LanguageResult(lang, conf, False, "detected")
