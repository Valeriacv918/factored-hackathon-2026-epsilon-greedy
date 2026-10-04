"""Router del Triage (estado TRIAGE): CÓDIGO, nunca el LLM.

Recibe el mensaje del cliente y lo que "opinó" el LLM (Understanding),
y decide a dónde sigue la conversación (TriageDecision).

Reglas, EN ESTE ORDEN (gana la primera que se cumpla):

  1. Palabras de emergencia en el texto (is_emergency)
       → Route.EMERGENCY, intent=Intent.EMERGENCY, reason="emergency_keyword"
     Va primero para proteger el dinero: aunque el LLM diga otra cosa,
     haya fallado o el cliente también pida un humano.

  2. Pide un humano: por palabras (asks_for_human) O porque el LLM lo detectó (wants_human)
       → Route.ESCALATION, intent=la del LLM, reason="wants_human"
     Guardamos la intención del LLM: si era not_me, el ticket tiene más prioridad.

  3. El LLM no está seguro (confidence < CONFIDENCE_THRESHOLD)
       → Route.CLARIFY_INTENT, intent=None, reason="low_confidence"
     También cubre cuando el LLM falló (FALLBACK tiene confianza 0).

  4. Seguir la intención del LLM, con reason="llm_intent":
       Intent.EMERGENCY                    → Route.EMERGENCY
       Intent.NOT_ME o Intent.CHARGE_ERROR → Route.FIND_TRANSACTION
       Intent.OTHER                        → Route.OUT_OF_SCOPE

En TODOS los casos guarda lo que opinó el LLM: understanding=understanding
"""
from bank_agent.nodes.triage_agent.rules import asks_for_human, is_emergency
from bank_agent.nodes.triage_agent.schemas import Intent, Route, TriageDecision, Understanding

# Por debajo de este valor se muestran botones. Es provisional:
# lo ajustaremos con la evaluación (paso 6).
CONFIDENCE_THRESHOLD = 0.7


def decide(text: str, understanding: Understanding) -> TriageDecision:
    u = understanding   # nombre corto para escribir menos

    # Regla 1: emergencia
    if is_emergency(text):
      return TriageDecision(
        route=Route.EMERGENCY,
        intent=Intent.EMERGENCY,
        reason="emergency_keyword",
        understanding=u,
      )

    # Regla 2: pide humano
    if asks_for_human(text) or u.wants_human:
      return TriageDecision(
          route=Route.ESCALATION,
          intent=u.intent,
          reason="wants_human",
          understanding=u,
        )

    # Regla 3: confianza baja
    if u.confidence < CONFIDENCE_THRESHOLD:
      return TriageDecision(
        route=Route.CLARIFY_INTENT,
        intent=None,
        reason="low_confidence",
        understanding=u,
      )

    # Regla 4: seguir la intención del LLM
    if u.intent == Intent.EMERGENCY:
      return TriageDecision(
        route=Route.EMERGENCY,
        intent=u.intent,
        reason="llm_intent",
        understanding=u,
      )

    if u.intent in (Intent.NOT_ME, Intent.CHARGE_ERROR):
      return TriageDecision(
        route=Route.FIND_TRANSACTION,
        intent=u.intent,
        reason="llm_intent",
        understanding=u,
      )

    # Si llegó hasta aquí, es Intent.OTHER: no es algo que atendamos
    return TriageDecision(
        route=Route.OUT_OF_SCOPE,
        intent=Intent.OTHER,
        reason="llm_intent",
        understanding=u,
    )

