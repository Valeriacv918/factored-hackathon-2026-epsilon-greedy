"""Isolated charge-error route: classify status, persist explanation, end."""
from langgraph.types import interrupt
from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.nodes import charge_error
from bank_agent.nodes.common import HandoffRequested, require_session, number

def terminal(outcome, response, **extra):
    return dict(route="end", outcome=outcome, response=response, **extra)

def build_nodes(services, policy):
    def extract(s):
        parsed = services.understand(s.get("charge_input") or s["message"], s["language"])
        if parsed.get("wants_human"):
            return terminal("human_requested", "Solicitud de atención humana identificada; no se creó un ticket.")
        if parsed.get("intent") in {"not_me", "emergency"}:
            return terminal("outside_charge_test", "La solicitud requiere otra ruta; termina esta prueba de error en un cargo.")
        slots = parsed.get("slots")
        if not isinstance(slots, dict):
            raise ServiceFailure("Invalid slots")
        return dict(route="charge_find", phase="find", slots={**s.get("slots", {}), **slots}, charge_input="")

    def find(s):
        result = services.tool("find_transactions", session_ref=s["session_ref"],
            customer_id=s["customer_id"], arguments={"slots":s.get("slots",{}),
            "limit":3, "window_days":policy.window_days})
        candidates = result.get("transactions", [])
        if any(t.get("customer_id") != s["customer_id"] for t in candidates):
            raise ServiceFailure("Ownership mismatch")
        if not candidates or result.get("has_more"):
            if s.get("clarification_attempts",0) >= policy.max_clarifications:
                return terminal("transaction_unresolved", "No se pudo identificar el cargo con los datos proporcionados.")
            return dict(route="charge_details", phase="clarify", charge_candidates=[],
                        reason="no_matches" if not candidates else "too_many_matches")
        return dict(route="charge_select", phase="select", charge_candidates=candidates)

    def details(s):
        prefix = "No encontré coincidencias con esos filtros. " if s.get("reason") == "no_matches" else "Hay varios movimientos posibles. "
        reply = interrupt({"kind":"transaction_details","message":prefix +
            "Indica o corrige la fecha (o un rango de fechas), el monto y la moneda si la conoces. "
            "El comercio es opcional; puedes omitirlo si no aparece."})
        require_session(s,services)
        if not isinstance(reply,dict) or not isinstance(reply.get("text"),str) or not reply["text"].strip():
            raise ValueError("Expected nonempty text")
        return dict(route="charge_extract", phase="extract", charge_input=reply["text"].strip(),
            clarification_attempts=s.get("clarification_attempts",0)+1)

    def select(s):
        candidates=s["charge_candidates"]
        reply=interrupt({"kind":"select_transaction","message":"Selecciona el cargo que quieres revisar.",
            "options":[t["id"] for t in candidates]+["none","human"],
            "transactions":[{k:t.get(k) for k in ("id","date","amount","currency")} | {"date":t.get("local_date") or t.get("date"),
                         "timezone":t.get("customer_timezone"), "merchant":t.get("merchant") or "Sin comercio informado"} for t in candidates]})
        require_session(s,services)
        choice=reply.get("choice") if isinstance(reply,dict) else None
        if choice=="human":
            return terminal("human_requested","Solicitud de atención humana identificada; no se creó un ticket.")
        if choice=="none":
            if s.get("clarification_attempts",0)>=policy.max_clarifications:
                return terminal("transaction_unresolved","No se pudo identificar el cargo.")
            return dict(route="charge_details",phase="clarify")
        tx=next((t for t in candidates if t["id"]==choice),None)
        if tx is None:
            raise ValueError("Select an offered transaction")
        score=number(tx.get("fraud_score"))
        if score is None:
            return terminal("human_required","El cargo no tiene un puntaje de riesgo válido para continuar.", reason="missing_fraud_score")
        if score>policy.fraud_score:
            return terminal("ready_for_fraud","El cargo requiere revisión de fraude; esa ruta queda fuera de esta prueba.",
                transaction=tx, reason="fraud_score")
        return dict(route="charge_error",phase="start",transaction=tx)

    def evaluate(s):
        status = s["transaction"]["status"]
        if status == "Approved":
            return terminal("approved", "La transacción figura aprobada.")
        if status not in charge_error.EXPLANATIONS:
            return terminal("unknown_status", "No fue posible interpretar el estado de la transacción.")
        rule, es, pt = charge_error.EXPLANATIONS[status]
        return dict(route="charge_save", phase="save", explanation_rule=rule,
                    response=pt if s.get("language") == "pt" else es)

    def save(s):
        receipt = services.tool("save_charge_explanation", session_ref=s["session_ref"],
            customer_id=s["customer_id"], arguments={
                "conversation_id":s["conversation_id"], "transaction_id":s["transaction"]["id"],
                "observed_status":s["transaction"]["status"]})
        if receipt.get("verified") is not True or not receipt.get("result_id"):
            raise ServiceFailure("Explanation receipt not verified")
        if (receipt.get("transaction_id") != s["transaction"]["id"]
                or receipt.get("observed_status") != s["transaction"]["status"]
                or receipt.get("rule_id") != s["explanation_rule"]):
            raise ServiceFailure("Explanation receipt mismatch")
        return terminal("explained", s["response"], explanation_result_id=receipt["result_id"])

    def guard(fn):
        def run(s):
            try:
                require_session(s,services)
                return fn(s)
            except SessionExpired:
                return terminal("authentication_required","La sesión expiró. Inicia una nueva conversación.",
                    authenticated=False,customer_id="")
            except HandoffRequested:
                return terminal("human_requested","Solicitud de atención humana identificada; no se creó un ticket.")
            except ServiceFailure:
                return terminal("service_unavailable","No fue posible completar y verificar el resultado. No se confirma el guardado.")
        return run

    return {name:guard(fn) for name,fn in {
        "charge_extract":extract,"charge_find":find,"charge_details":details,
        "charge_select":select,"charge_error":evaluate,"charge_save":save}.items()}
