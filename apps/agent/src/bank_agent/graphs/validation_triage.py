"""Validation + triage, with an optional isolated read-only charge-error test route.

Keep the model call and the interrupt in separate nodes: resuming an interrupt
must not replay a verification attempt or a model call. Agent sessions live in
McpServices for this local process, not in serializable graph state.
"""
import logging
from copy import deepcopy
from langgraph.graph import START, END, StateGraph
from langgraph.types import interrupt
from bank_agent.graphs.state import ConversationState
from bank_agent.nodes.triage_agent.router import decide
from bank_agent.nodes.triage_agent.schemas import Understanding, Intent, Route, Slots

logger = logging.getLogger(__name__)
CHOICES = ["emergency", "not_me", "charge_error", "other", "human"]

def build_graph(services, *, checkpointer, policy=None, test_charge_error=False, test_fraud=False,
                test_escalation=False):
    if test_escalation and not test_fraud:
        raise ValueError("test_escalation requires test_fraud")

    def fail(s, reason, message):
        s.update(route="end", reason=reason, outcome="service_unavailable", response=message)
        return s

    def validated(s):
        agent = services.validation_agent(s["conversation_id"])
        cid = services.validate_session(agent.session.session_id)
        return agent, cid

    def validator(s):
        s = deepcopy(s)
        s["phase"] = "validate"
        try:
            agent = services.validation_agent(s["conversation_id"])
            result = agent.chat(s.get("validation_input", s["message"]))
            s["language"] = result.get("language") or agent.session.language or "es"
            cid = services.validate_session(agent.session.session_id)
            if cid:
                s.update(customer_id=cid, session_ref=agent.session.session_id,
                         authenticated=True, route="request_wait",
                         response="Identidad verificada. Describe la solicitud que deseas atender.",
                         validation_status="VERIFIED")
            elif result.get("next_step") == "handoff_human":
                s.update(route="end", authenticated=False, outcome="human_required",
                         reason=result.get("status") or "validation_failed",
                         validation_status=result.get("status"),
                         response="No fue posible validar tu identidad. Se requiere revisión humana; no se ha creado una derivación.")
            else:
                s.update(route="validation_wait", authenticated=False,
                         validation_status=result.get("status"),
                         response=result.get("reply") or "Indica tu número de documento, fecha de nacimiento y número de producto.")
        except Exception as exc:
            logger.warning("Validation failed (%s)", type(exc).__name__)
            fail(s, "validation_unavailable", "La validación no está disponible. No se consultarán tus productos.")
        # Do not carry identity factors into triage or debug output.
        s["message"] = ""
        s["validation_input"] = ""
        return s

    def validation_wait(s):
        value = interrupt({"kind": "validation_details", "message": s["response"]})
        if not isinstance(value, dict) or not isinstance(value.get("text"), str) or not value["text"].strip():
            raise ValueError("Expected nonempty text")
        return {**s, "validation_input": value["text"].strip(), "route": "validator_agent", "phase": "await_identity"}

    def request_wait(s):
        value = interrupt({"kind": "request_details",
                           "message": "Identidad verificada. ¿Qué necesitas hacer ahora?"})
        if not isinstance(value, dict) or not isinstance(value.get("text"), str) or not value["text"].strip():
            raise ValueError("Expected nonempty text")
        return {**s, "message": value["text"].strip(), "route": "triage_agent", "phase": "await_request"}

    def triage(s):
        s = deepcopy(s)
        s["phase"] = "classify"
        try:
            _, cid = validated(s)
            if not cid or cid != s.get("customer_id"):
                s.update(route="end", authenticated=False, customer_id="",
                         outcome="authentication_required", response="La sesión expiró. Inicia una nueva conversación.")
                return s
            choice = s.pop("triage_choice", None)
            if choice:
                u = Understanding(intent=Intent.OTHER if choice == "human" else Intent(choice),
                                  confidence=1.0, wants_human=choice == "human", slots=Slots())
            else:
                u = services.triage_understand(s["message"])
                u = u if isinstance(u, Understanding) else Understanding.model_validate(u)
            decision = decide(s["message"], u)
            s.update(intent=decision.intent.value if decision.intent else None,
                     intent_confidence=u.confidence, slots=u.slots.model_dump(exclude_none=True),
                     reason=decision.reason, triage_route=decision.route.value)
            if decision.route == Route.CLARIFY_INTENT:
                s.update(route="triage_wait", response="¿Cuál de estas opciones describe tu solicitud?")
            elif decision.route == Route.EMERGENCY:
                s.update(route="end", outcome="ready_for_card_emergency",
                         response="Clasificación: emergencia de tarjeta. La ejecución de ese agente está pendiente; no se ha bloqueado ninguna tarjeta.")
            elif decision.route == Route.FIND_TRANSACTION and ((test_charge_error and decision.intent == Intent.CHARGE_ERROR) or (test_fraud and decision.intent in {Intent.NOT_ME, Intent.CHARGE_ERROR})):
                s.update(route="charge_extract", phase="extract", slots={})
            elif decision.route == Route.FIND_TRANSACTION:
                s.update(route="end", outcome="ready_for_transaction_search",
                         response="Clasificación: revisar un cargo. El siguiente paso es buscar la transacción; esta prueba termina antes de esa búsqueda.")
            elif decision.route == Route.ESCALATION:
                if test_escalation:
                    priority = "P2" if decision.intent in {Intent.NOT_ME, Intent.EMERGENCY} else "P3"
                    s.update(route="escalation", phase="start", reason="requested_human",
                             queue="general", priority=priority)
                else:
                    s.update(route="end", outcome="human_requested",
                             response="Solicitud de atención humana identificada. No se ha creado un ticket.")
            else:
                s.update(route="end", outcome="out_of_scope",
                         response="La solicitud está fuera del alcance de tarjetas y revisión de cargos.")
        except Exception as exc:
            logger.warning("Triage failed (%s)", type(exc).__name__)
            fail(s, "triage_unavailable", "No fue posible clasificar la solicitud.")
        return s

    def triage_wait(s):
        value = interrupt({"kind": "clarify_intent", "message": s["response"], "options": CHOICES})
        if not isinstance(value, dict) or value.get("choice") not in CHOICES:
            raise ValueError("Choose one of the supplied options")
        return {**s, "triage_choice": value["choice"], "route": "triage_agent", "phase": "await_intent"}

    nodes = {"validator_agent": validator, "validation_wait": validation_wait,
             "request_wait": request_wait, "triage_agent": triage, "triage_wait": triage_wait}
    if test_charge_error or test_fraud:
        from bank_agent.graphs.charge_test import build_nodes
        from bank_agent.graphs.policy import Policy
        nodes.update(build_nodes(services, policy or Policy(), test_fraud=test_fraud,
                     test_escalation=test_escalation))
        if test_fraud:
            from bank_agent.graphs.fraud_test import build_escalation_node, build_node
            nodes["fraud_agent"] = build_node(services, policy or Policy(), connect_escalation=test_escalation)
            if test_escalation:
                nodes["escalation"] = build_escalation_node(services, policy or Policy())
    builder = StateGraph(ConversationState)
    def wrap(name, fn):
        def run(state):
            result = fn(deepcopy(state))
            result["trace"] = state.get("trace", []) + [{
                "node": name, "phase": result.get("phase", state.get("phase")), "next": result["route"],
                "at": services.now().isoformat(),
            }]
            return result
        return run
    for name, fn in nodes.items():
        builder.add_node(name, wrap(name, fn))
        builder.add_conditional_edges(name, lambda s: s["route"], {n: n for n in nodes} | {"end": END})
    builder.add_edge(START, "validator_agent")
    return builder.compile(checkpointer=checkpointer)
