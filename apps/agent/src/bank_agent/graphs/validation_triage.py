"""Validation + triage, with an optional isolated read-only charge-error test route.

Keep the model call and the interrupt in separate nodes: resuming an interrupt
must not replay a verification attempt or a model call. Agent sessions live in
McpServices for this local process, not in serializable graph state.

Login is a FORM with no LLM (same pieces as nodes/validator_agent in the disputes graph):
document, date of birth and product number go to services.verify_identity -> MCP, so no
model ever sees identity data. The first message is dropped for the same reason.
"""
import logging
from copy import deepcopy
from langgraph.graph import START, END, StateGraph
from langgraph.types import interrupt
from bank_agent.graphs.state import ConversationState
from bank_agent.observability import logged_step
from bank_agent.nodes.triage_agent.router import decide
from bank_agent.nodes.common import say
from bank_agent.nodes.validator_agent import FIELDS, MAX_FORM_PROMPTS, identity_form_values, identity_retry_message
from bank_agent.nodes.triage_agent.schemas import Understanding, Intent, Route, Slots


logger = logging.getLogger(__name__)
CHOICES = ["emergency", "not_me", "charge_error", "other", "human"]

def build_graph(services, *, checkpointer, policy=None, test_charge_error=False, test_fraud=False,
                test_escalation=False, test_card_emergency=False):
    if test_escalation and not (test_fraud or test_card_emergency):
        raise ValueError("test_escalation requires test_fraud or test_card_emergency")

    def fail(s, reason, message):
        s.update(route="end", reason=reason, outcome="service_unavailable", response=message)
        return s

    def validated(s):
        return services.validate_session(s.get("session_ref"))

    def validator(s):
        """No LLM and no pause: detect the language and show the login form.
        The first message is dropped because it may contain identity factors."""
        s = deepcopy(s)
        s["phase"] = "validate"
        detect = getattr(services, "detect_language", None)
        s["language"] = s.get("language") or (detect(s.get("message", "")) if detect else None) or "es"
        s.update(route="validation_wait", authenticated=False, identity_prompts=0,
                 response=say(s, "Para ayudarte necesito verificar tu identidad.",
                              "Para ajudar, preciso verificar sua identidade."))
        s["message"] = ""
        s["validation_input"] = ""
        return s

    def validation_wait(s):
        """Login FORM: the three factors go to services.verify_identity (IdentityValidator -> MCP),
        never to an LLM. Verification runs after the pause, so resuming never repeats an attempt."""
        prompts = s.get("identity_prompts", 0)
        if prompts >= MAX_FORM_PROMPTS:
            return {**s, "route": "end", "outcome": "human_required", "reason": "too_many_forms",
                    "response": "No fue posible validar tu identidad. Se requiere revisión humana; no se ha creado una derivación."}
        value = interrupt({"kind": "identity_form", "language": s.get("language"), "message": s["response"],
                           "fields": list(FIELDS), "hints": {"date_of_birth": "AAAA-MM-DD / DD/MM/AAAA"}})
        fields = identity_form_values(value)
        s = deepcopy(s)
        s["phase"] = "await_identity"
        try:
            result = services.verify_identity(s["conversation_id"], **fields)
            status = result.get("status")
            cid = services.validate_session(result["session_ref"]) if status in {"VERIFIED", "ALREADY_VERIFIED"} else None
        except Exception as exc:
            logger.warning("Validation failed (%s)", type(exc).__name__)
            status, cid = "SERVICE_UNAVAILABLE", None
        if cid:
            s.update(customer_id=cid, session_ref=result["session_ref"], authenticated=True, route="request_wait",
                     response="Identidad verificada. Describe la solicitud que deseas atender.",
                     validation_status="VERIFIED")
        elif status == "LOCKED":
            s.update(route="end", authenticated=False, outcome="human_required", reason="LOCKED",
                     validation_status=status,
                     response="No fue posible validar tu identidad. Se requiere revisión humana; no se ha creado una derivación.")
        elif status in {"FAILED", "INVALID_FORMAT", "MISSING_FIELDS"}:
            s.update(route="validation_wait", authenticated=False, validation_status=status,
                     response=identity_retry_message(s, result), identity_prompts=prompts + 1)
        else:
            fail(s, "validation_unavailable", "La validación no está disponible. No se consultarán tus productos.")
            s["authenticated"] = False
        return s

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
            cid = validated(s)
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
                if test_card_emergency:
                    s.update(route="card_emergency_agent", phase="start", intent="emergency")
                else:
                    s.update(route="end", outcome="ready_for_card_emergency",
                             response="Clasificación: emergencia de tarjeta. ...")
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
                     test_escalation=test_escalation, test_card_emergency=test_card_emergency))
        if test_fraud:
            from bank_agent.graphs.fraud_test import build_escalation_node, build_node
            nodes["fraud_agent"] = build_node(services, policy or Policy(), connect_escalation=test_escalation)
            if test_escalation:
                nodes["escalation"] = build_escalation_node(services, policy or Policy())
    if test_card_emergency:
        from bank_agent.graphs.emergency_test import build_node as build_card_emergency_node
        from bank_agent.graphs.fraud_test import build_escalation_node
        from bank_agent.graphs.policy import Policy
        nodes["card_emergency_agent"] = build_card_emergency_node(
            services, policy or Policy(), connect_fraud=test_fraud, connect_escalation=test_escalation)
        if test_escalation:
            nodes.setdefault("escalation", build_escalation_node(services, policy or Policy()))
    builder = StateGraph(ConversationState)
    def wrap(name, fn):
        def run(state):
            with logged_step(state.get("conversation_id"), name, state.get("phase")) as step:
                result = fn(deepcopy(state))
                step.update(next=result["route"], phase=result.get("phase", state.get("phase")),
                            state={**state, **result})
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
