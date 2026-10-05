"""Adapter for the existing fraud node in the isolated integration graph."""
from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.nodes import fraud_agent
from bank_agent.nodes.common import HandoffRequested, require_session
from bank_agent.graphs.charge_test import terminal

def build_node(services, policy):
    def run(s):
        try:
            require_session(s, services)
            if s.get("turns", 1) >= policy.max_turns:
                return terminal("human_required", "Se alcanzó el límite de esta prueba. Se requiere revisión humana.",
                                reason="turn_limit", queue="fraud", priority="P2")
            result = fraud_agent.run(s, services, policy)
            if result["route"] == "triage_agent":
                # Existing fraud agent asks for the next unrecognized transaction.
                return {**result, "route":"charge_details", "phase":"clarify",
                        "charge_candidates":[], "charge_input":"", "reason":"",
                        "clarification_attempts":0, "transaction":{}, "card_id":None, "account_id":None}
            if result["route"] == "escalation":
                return {**result, **terminal("human_required",
                    "Se requiere revisión humana. No se creó una derivación en esta prueba.",
                    reason=result.get("reason"), queue=result.get("queue"), priority=result.get("priority"))}
            if result.get("outcome") == "fraud_intake_complete":
                result["response"] = "Simulación completada en sandbox. " + result["response"]
            return result
        except SessionExpired:
            return terminal("authentication_required", "La sesión expiró. Inicia una nueva conversación.",
                            authenticated=False, customer_id="")
        except HandoffRequested as exc:
            return terminal("human_requested", "Solicitud de atención humana identificada; no se creó una derivación.",
                            reason=exc.reason)
        except ServiceFailure:
            return terminal("service_unavailable",
                "No se pudo completar y verificar la operación. Revisa los recibos antes de reintentar.",
                reason="fraud_tool_failure")
    return run
