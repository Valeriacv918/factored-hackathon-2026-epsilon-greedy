"""Adapter for the existing card emergency node in the isolated integration graph."""

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.graphs.charge_test import terminal
from bank_agent.nodes import card_emergency_agent
from bank_agent.nodes.common import HandoffRequested, require_session


def build_node(services, policy, *, connect_fraud=False, connect_escalation=False):
    def run(s):
        try:
            require_session(s, services)
            if s.get("turns", 1) >= policy.max_turns:
                return terminal("human_required", "Se alcanzó el límite de esta prueba. Se requiere revisión humana.",
                                reason="turn_limit", queue="cards", priority="P2")
            result = card_emergency_agent.run(s, services, policy)
            if result["route"] == "triage_agent":
                if connect_fraud:
                    return {**result, "route": "charge_details", "phase": "clarify", "charge_candidates": [],
                            "charge_input": "", "reason": "", "clarification_attempts": 0, "transaction": {}}
                return {**result, **terminal("ready_for_transaction_search",
                        "Tarjeta protegida. El siguiente paso es buscar el cargo; esta prueba termina aquí.")}
            if result["route"] == "escalation" and not connect_escalation:
                return {**result, **terminal("human_required",
                        "Se requiere revisión humana. No se creó una derivación en esta prueba.",
                        reason=result.get("reason"), queue=result.get("queue"), priority=result.get("priority"))}
            return result
        except SessionExpired:
            return terminal("authentication_required", "La sesión expiró. Inicia una nueva conversación.",
                            authenticated=False, customer_id="")
        except HandoffRequested as exc:
            if connect_escalation:
                return {"route": "escalation", "phase": "start", "reason": exc.reason, "queue": "general", "priority": "P2"}
            return terminal("human_requested", "Solicitud de atención humana identificada; no se creó una derivación.",
                            reason=exc.reason)
        except ServiceFailure:
            return terminal("service_unavailable",
                            "No se pudo completar y verificar el bloqueo. Revisa los recibos antes de reintentar.",
                            reason="card_emergency_tool_failure")
    return run