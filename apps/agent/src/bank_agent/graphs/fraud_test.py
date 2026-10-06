"""Adapter for the existing fraud node in the isolated integration graph."""
from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.nodes import fraud_agent
from bank_agent.nodes.common import HandoffRequested, require_session, say
from bank_agent.graphs.charge_test import terminal
from bank_agent.observability import log_failure

def build_node(services, policy, *, connect_escalation=False):
    def run(s):
        try:
            require_session(s, services)
            if s.get("turns", 1) >= policy.max_turns:
                if connect_escalation:
                    return dict(route="escalation", phase="start", reason="turn_limit", queue="fraud", priority="P2")
                return terminal("human_required", say(s, "Se alcanzó el límite de esta prueba. Se requiere revisión humana.", "O limite deste teste foi atingido. É necessária uma revisão humana."),
                                reason="turn_limit", queue="fraud", priority="P2")
            result = fraud_agent.run(s, services, policy)
            if result["route"] == "triage_agent":
                # Existing fraud agent asks for the next unrecognized transaction.
                return {**result, "route":"charge_details", "phase":"clarify",
                        "charge_candidates":[], "charge_input":"", "reason":"",
                        "clarification_attempts":0, "transaction":{}, "card_id":None, "account_id":None}
            if result["route"] == "escalation" and not connect_escalation:
                return {**result, **terminal("human_required",
                    say(s, "Se requiere revisión humana. No se creó una derivación en esta prueba.", "É necessária uma revisão humana. Nenhum encaminhamento foi criado neste teste."),
                    reason=result.get("reason"), queue=result.get("queue"), priority=result.get("priority"))}
            if result.get("outcome") == "fraud_intake_complete":
                result["response"] = say(s, "Simulación completada en sandbox. ", "Simulação concluída no sandbox. ") + result["response"]
            return result
        except SessionExpired:
            return terminal("authentication_required", say(s, "La sesión expiró. Inicia una nueva conversación.", "A sessão expirou. Inicie uma nova conversa."),
                            authenticated=False, customer_id="")
        except HandoffRequested as exc:
            if connect_escalation:
                return {"route": "escalation", "phase": "start", "reason": exc.reason,
                        "queue": "general", "priority": "P2" if s.get("intent") in {"not_me", "emergency"} else "P3"}
            return terminal("human_requested", say(s, "Solicitud de atención humana identificada; no se creó una derivación.", "Solicitação de atendimento humano identificada; nenhum encaminhamento foi criado."),
                            reason=exc.reason)
        except ServiceFailure as exc:
            log_failure(exc, "fraud_tool_failure")
            return terminal("service_unavailable",
                say(s, "No se pudo completar y verificar la operación.", "Não foi possível concluir e verificar a operação."),
                reason="fraud_tool_failure")
    return run


def build_escalation_node(services, policy):
    from bank_agent.nodes import escalation

    def run(s):
        try:
            require_session(s, services)
            return escalation.run(s, services, policy)
        except SessionExpired:
            return terminal("authentication_required", say(s, "La sesión expiró. Inicia una nueva conversación.", "A sessão expirou. Inicie uma nova conversa."),
                            authenticated=False, customer_id="")
        except ServiceFailure as exc:
            log_failure(exc, "escalation_tool_failure")
            return terminal("service_unavailable",
                            say(s, "No se pudo completar y verificar la derivación.", "Não foi possível concluir e verificar o encaminhamento."),
                            reason="escalation_tool_failure")

    return run
