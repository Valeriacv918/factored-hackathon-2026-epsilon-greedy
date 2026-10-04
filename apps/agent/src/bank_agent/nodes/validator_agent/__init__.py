"""Nodo validator_agent del grafo de disputas (STATE_MACHINE2: DETECT_LANGUAGE + VALIDATE_SESSION).

Reemplaza a security_language. Fases separadas para que retomar una pausa nunca
repita un intento de login ni una llamada al LLM (mismo criterio que graphs/validation_triage.py):

- start:    idioma (lingua; si duda, botones). Si la sesión ya es válida (web app, DEV_SESSIONS)
            sigue directo a understanding; si no, pasa a identify.
- identify: ValidationAgent.chat() -> LLM + IdentityValidator + MCP verify_identity. Sin pausa.
- wait:     pausa para que el cliente escriba sus datos de identidad.
- request:  pausa "¿En qué te ayudo?" ya autenticado; ese texto es el que clasifica understanding.
"""
from langgraph.types import interrupt

from bank_agent.nodes.common import ask, finish, go, say

TEXT = "text"


def _text(reply):
    if not isinstance(reply, dict) or not isinstance(reply.get(TEXT), str) or not reply[TEXT].strip():
        raise ValueError("Expected {'text': <nonempty text>}.")
    return reply[TEXT].strip()


def run(s, services, policy):
    phase = s.get("phase", "start")

    if phase == "start":
        language = s.get("language") or services.detect_language(s["message"])
        if language not in {"es", "pt"}:
            language = ask(s, services, "language", ["es", "pt"],
                           "Selecciona tu idioma: Español / Português.",
                           "Selecione seu idioma: Español / Português.")
        s["language"] = language
        reported_at = s.get("reported_at", services.now().isoformat())
        customer = services.validate_session(s["session_ref"])
        if customer:   # ya autenticado afuera (web app, DEV_SESSIONS): sin segundo login
            return go("understanding", language=language, customer_id=customer, reported_at=reported_at)
        return go("validator_agent", "identify", language=language, reported_at=reported_at,
                  validation_input=s["message"])

    if phase == "identify":
        new_agent = getattr(services, "validation_agent", None)
        if new_agent is None:   # servicios sin login (tests, demo sin validador)
            return finish(s, "authentication_required", "Inicia sesión para continuar.",
                          "Entre na sua conta para continuar.")
        try:
            agent = new_agent(s["conversation_id"])
            result = agent.chat(s.get("validation_input") or "")
            customer = services.validate_session(agent.session.session_id)
        except Exception:   # LLM o MCP caídos: nunca autenticar por defecto
            return {**finish(s, "service_unavailable", "La validación no está disponible. No se consultarán tus productos.",
                             "A validação não está disponível. Seus produtos não serão consultados."),
                    "validation_input": "", "message": ""}
        cleared = {"validation_input": "", "message": ""}   # los datos de identidad no siguen en el estado
        if customer:
            return go("validator_agent", "request", session_ref=agent.session.session_id, customer_id=customer,
                      validation_status="VERIFIED", **cleared)
        if result.get("next_step") == "handoff_human":
            return {**finish(s, "human_required",
                             "No fue posible validar tu identidad. Comunícate con la línea de atención.",
                             "Não foi possível validar sua identidade. Entre em contato com a central de atendimento."),
                    "validation_status": result.get("status"), **cleared}
        return go("validator_agent", "wait", validation_status=result.get("status"),
                  response=result.get("reply") or say(s, "Indica tu número de documento, fecha de nacimiento y número de producto.",
                                                       "Informe seu número de documento, data de nascimento e número de produto."),
                  **cleared)

    if phase == "wait":
        reply = interrupt({"kind": "validation_details", "language": s.get("language"),
                           "message": s.get("response"), "fields": [TEXT]})
        return go("validator_agent", "identify", validation_input=_text(reply), turns=s.get("turns", 1) + 1)

    # phase == "request": autenticado; ahora sí, la solicitud del cliente.
    reply = interrupt({"kind": "request_details", "language": s.get("language"),
                       "message": say(s, "Identidad verificada. ¿En qué te puedo ayudar?",
                                      "Identidade verificada. Como posso ajudar?"),
                       "fields": [TEXT]})
    return go("understanding", message=_text(reply), turns=s.get("turns", 1) + 1)