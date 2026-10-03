"""Reglas fijas del Triage (código, sin LLM).

Dos usos:
1. REGLAS DE SEGURIDAD que se aplican siempre, digan lo que diga el LLM
   (STATE_MACHINE.md, reglas globales 1 y 2):
   - palabras de robo/pérdida/emergencia  → emergencia de tarjeta
   - pedir una persona         → escalar a humano
2. BASELINE: un clasificador simple de palabras clave. Sirve para comparar:
   si el LLM no le gana al baseline en la evaluación, el LLM no se justifica.
"""
import re
import unicodedata

from bank_agent.nodes.triage_agent.schemas import Intent, Understanding


# ============================================================================
# Utilidades (ya están listas, no hay que cambiarlas)
# ============================================================================

def normalize(text: str) -> str:
    """Minúsculas y sin tildes: 'Perdí mi CARTÃO' → 'perdi mi cartao'."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def contains_any(text: str, phrases: list[str]) -> bool:
    """True si el texto contiene alguna frase COMPLETA de la lista.
    \\b = borde de palabra: 'robo' encuentra 'me robo' pero no 'robot'."""
    clean = normalize(text)
    return any(re.search(rf"\b{re.escape(p)}\b", clean) for p in phrases)


# ============================================================================
# TU PARTE 1: las frases
# - Escríbelas en minúsculas y SIN tildes ("perdi", no "Perdí").
# - NO mires evals/triage/messages.csv mientras las escribes.
# - Corre los tests para ver cuáles frases te faltan.
# ============================================================================

EMERGENCY_PHRASES = [
    # español
    "me robaron",
    "perdi mi tarjeta",
    "me clonaron",
    "me copiaron los datos",
    "me la retuvieron",
    "urgente",
    "me estafaron",
    "me engañaron",
    "perdi mi billetera",
    "perdi mi cartera",
    "me tumbaron",
    "me robaron los datos de la tarjeta",
    "tengo una emergencia",
    "me robaron el celular y tengo la app del banco ahi",
    "necesito ayuda urgente",
    "tengo mi cuenta comprometida",
    "No puedo entrar a mi cuenta",
    "no puedo acceder a mi cuenta",
    "bloqueenme la tarjeta por favor",
    "se me quedo la tarjeta en el cajero"




    # TODO: perder la tarjeta, clonación, pedir bloqueo...
    # portugués
    "roubaram",
    # TODO
]

HUMAN_PHRASES = [
    "asesor",
    "persona",
    "humano",
    "hablar con alguien",
    "quiero hablar con alguien",
    "quiero hablar con un asesor",
    "asesora",
    "asistente al cliente",
    "atencion al usuario",
    "servicio al cliente"
    
    # TODO: español y portugués
]

NOT_ME_PHRASES = [
    "no reconozco",
    "pago no reconocido",
    "no realice",
    "no hice",
    "me hackearon",
     "me vaciaron la cuenta",
    # TODO
]

CHARGE_ERROR_PHRASES = [
    "multiples veces",
    "varias veces",
    "dos veces",
    "tres veces",
    "cobro mal",
    "incorrecto",
    "erroneo",
    "equivocado",
    "valor no coincide",
    "valor incorrecto",
    "no autorice",


    # TODO
]


# ============================================================================
# Reglas de seguridad (ya están listas)
# ============================================================================

def is_emergency(text: str) -> bool:
    return contains_any(text, EMERGENCY_PHRASES)


def asks_for_human(text: str) -> bool:
    return contains_any(text, HUMAN_PHRASES)


# ============================================================================
# TU PARTE 2: el baseline
# ============================================================================

def baseline_understand(text: str) -> Understanding:
    """Clasifica solo con palabras clave. Devuelve el mismo formato que el LLM
    (Understanding), para poder evaluarlos de la misma forma.

    TODO: revisa en este orden y quédate con el PRIMERO que coincida:
      1. ¿es emergencia de tarjeta?           → Intent.CARD_EMERGENCY, confianza 0.9
      2. ¿contiene una frase de NOT_ME?       → Intent.NOT_ME,         confianza 0.9
      3. ¿contiene una frase de CHARGE_ERROR? → Intent.CHARGE_ERROR,   confianza 0.9
      4. ninguna                              → Intent.OTHER,          confianza 0.5
    wants_human va aparte: asks_for_human(text).

    Pista: usa if / elif / else, y al final:
        return Understanding(intent=..., confidence=..., wants_human=...)
    """
    raise NotImplementedError("Escribe aquí el baseline")
