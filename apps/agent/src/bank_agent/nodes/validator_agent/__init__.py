"""Nodo validator_agent del grafo de disputas (STATE_MACHINE2: DETECT_LANGUAGE + VALIDATE_SESSION).

Login con FORMULARIO, sin LLM: el documento, la fecha de nacimiento y el producto van en
campos separados directo a IdentityValidator -> MCP verify_identity. Ningún LLM ve esos datos
(principio "el LLM nunca ve datos personales"); el LLM conversacional de agent.py no se usa aquí.

- start:    idioma (lingua; si duda, botones). Si la sesión ya es válida (web app, DEV_SESSIONS)
            sigue directo a triage_agent; si no, pasa a identify. El primer mensaje no se clasifica:
            puede traer datos de identidad.
- identify: pausa con el formulario; al responder, verifica (después de la pausa, así retomar
            nunca repite un intento). Datos que no coinciden -> formulario otra vez, con intentos.
- request:  pausa "¿En qué te ayudo?" ya autenticado; ese texto es el que clasifica triage_agent.
"""
from langgraph.types import interrupt

from bank_agent.nodes.common import ask, finish, go, say

TEXT = "text"
FIELDS = ("document_number", "date_of_birth", "product_number")
FIELD_NAMES = {   # (es, pt) para decir QUÉ campo corregir cuando el formato es inválido
    "document_number": ("número de documento", "número do documento"),
    "date_of_birth": ("fecha de nacimiento", "data de nascimento"),
    "product_number": ("número de producto", "número do produto"),
}
MAX_FORM_PROMPTS = 6   # tope de formularios: los errores de formato no gastan intentos de login


def _text(reply):
    if not isinstance(reply, dict) or not isinstance(reply.get(TEXT), str) or not reply[TEXT].strip():
        raise ValueError("Expected {'text': <nonempty text>}.")
    return reply[TEXT].strip()


def identity_form_values(reply):
    if not isinstance(reply, dict) or set(reply) != set(FIELDS) or not all(isinstance(reply[f], str) for f in FIELDS):
        raise ValueError(f"Expected exactly {{{', '.join(FIELDS)}}} as strings.")
    return {f: reply[f].strip() for f in FIELDS}


def identity_retry_message(s, result):
    status = result.get("status")
    if status == "FAILED":
        left = result.get("attempts_left")
        if left is None:
            return say(s, "Los datos no coinciden.", "Os dados não conferem.")
        return say(s, f"Los datos no coinciden. Te quedan {left} intentos.",
                   f"Os dados não conferem. Você tem mais {left} tentativas.")
    fields = [f for f in result.get("missing_fields", []) if f in FIELD_NAMES]
    pt = s.get("language") == "pt"
    names = ", ".join(FIELD_NAMES[f][1 if pt else 0] for f in fields) or ("os dados" if pt else "los datos")
    if status == "INVALID_FORMAT":
        return say(s, f"Revisa el formato de: {names}.", f"Verifique o formato de: {names}.")
    return say(s, f"Falta: {names}.", f"Falta: {names}.")


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
            return go("triage_agent", language=language, customer_id=customer, reported_at=reported_at)
        if getattr(services, "verify_identity", None) is None:   # servicios sin login (tests, demo sin validador)
            return finish(s, "authentication_required", "Inicia sesión para continuar.",
                          "Entre na sua conta para continuar.")
        return go("validator_agent", "identify", language=language, reported_at=reported_at,
                  message="", identity_prompts=0,
                  response=say(s, "Para ayudarte necesito verificar tu identidad.",
                               "Para ajudar, preciso verificar sua identidade."))

    if phase == "identify":
        prompts = s.get("identity_prompts", 0)
        if prompts >= MAX_FORM_PROMPTS:
            return finish(s, "human_required", "No fue posible validar tu identidad. Comunícate con la línea de atención.",
                          "Não foi possível validar sua identidade. Entre em contato com a central de atendimento.")
        reply = interrupt({"kind": "identity_form", "language": s.get("language"),
                           "message": s.get("response"), "fields": list(FIELDS),
                           "hints": {"date_of_birth": "AAAA-MM-DD / DD/MM/AAAA"}})
        fields = identity_form_values(reply)
        try:
            result = services.verify_identity(s["conversation_id"], **fields)
            status = result.get("status")
            customer = services.validate_session(result["session_ref"]) if status in {"VERIFIED", "ALREADY_VERIFIED"} else None
        except Exception:   # MCP caído u otra falla: nunca autenticar por defecto
            status, customer = "SERVICE_UNAVAILABLE", None
        if customer:
            return go("validator_agent", "request", session_ref=result["session_ref"], customer_id=customer,
                      validation_status="VERIFIED", authenticated=True)
        if status == "LOCKED":
            return {**finish(s, "human_required",
                             "Por seguridad bloqueamos la verificación por unos minutos. Comunícate con la línea de atención.",
                             "Por segurança, bloqueamos a verificação por alguns minutos. Entre em contato com a central de atendimento."),
                    "validation_status": status}
        if status in {"FAILED", "INVALID_FORMAT", "MISSING_FIELDS"}:
            return go("validator_agent", "identify", validation_status=status, response=identity_retry_message(s, result),
                      identity_prompts=prompts + 1)
        return {**finish(s, "service_unavailable", "La validación no está disponible. No se consultarán tus productos.",
                         "A validação não está disponível. Seus produtos não serão consultados."),
                "validation_status": "SERVICE_UNAVAILABLE"}

    # phase == "request": autenticado; ahora sí, la solicitud del cliente.
    reply = interrupt({"kind": "request_details", "language": s.get("language"),
                       "message": say(s, "Identidad verificada. ¿En qué te puedo ayudar?",
                                      "Identidade verificada. Como posso ajudar?"),
                       "fields": [TEXT]})
    return go("triage_agent", message=_text(reply), turns=s.get("turns", 1) + 1)
