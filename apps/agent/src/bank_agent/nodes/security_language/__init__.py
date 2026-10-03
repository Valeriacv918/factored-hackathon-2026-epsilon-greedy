from bank_agent.nodes.common import ask, finish, go


def run(s, services, policy):
    language = s.get("language") or services.detect_language(s["message"])
    if language not in {"es", "pt", "en"}:
        language = ask(s, services, "language", ["es", "pt", "en"],
                       "Selecciona tu idioma: Español / Português / English.",
                       "Selecione seu idioma: Español / Português / English.",
                       "Select your language: Español / Português / English.")
    s["language"] = language
    customer = services.validate_session(s["session_ref"])
    if not customer:
        return {**finish(s, "authentication_required", "Inicia sesión para continuar.",
                         "Entre na sua conta para continuar.", "Sign in to continue."), "language": language}
    return go("understanding", language=language, customer_id=customer,
              reported_at=s.get("reported_at", services.now().isoformat()))
