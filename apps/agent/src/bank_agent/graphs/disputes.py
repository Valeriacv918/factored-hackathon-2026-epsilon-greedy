"""Active graph for the dispute flow using the real agent modules under bank_agent.nodes."""
from copy import deepcopy

from langgraph.graph import END, START, StateGraph

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.graphs.policy import Policy
from bank_agent.graphs.state import ConversationState
from bank_agent.nodes.common import HandoffRequested, escalate, finish, require_session
from bank_agent.observability import logged_step
from bank_agent.nodes import (charge_error, escalation, fraud_agent, card_emergency_agent, validator_agent,
                              triage_agent)

NODES = {
    "validator_agent": validator_agent.run,
    "triage_agent": triage_agent.run,
    "card_emergency_agent": card_emergency_agent.run,
    "fraud_agent": fraud_agent.run,
    "charge_error": charge_error.run,
    "escalation": escalation.run,
}


def build_graph(services, *, checkpointer, policy=None):
    """Create the active graph with the supported agents only."""
    policy = policy or Policy()
    builder = StateGraph(ConversationState)

    def wrap(name, function):
        def node(state):
            with logged_step(state.get("conversation_id"), name, state.get("phase")) as step:
                result = run(state)
                step.update(next=result["route"], phase=result.get("phase", state.get("phase")))
                return result

        def run(state):
            s = deepcopy(state)
            try:
                if name != "validator_agent":
                    require_session(s, services)
                if name not in {"validator_agent", "escalation"} and s["turns"] >= policy.max_turns:
                    result = escalate("turn_limit", "general", "P2" if s.get("intent") == "not_me" else "P3")
                else:
                    result = function(s, services, policy)
            except SessionExpired:
                result = finish(s, "authentication_required", "Inicia sesión para continuar.", "Entre na sua conta para continuar.")
            except HandoffRequested as exc:
                result = escalate(exc.reason, "general", "P2" if s.get("intent") in {"not_me", "emergency"} else "P3")
            except ServiceFailure:
                if name in {"escalation", "validator_agent"}:
                    result = finish(s, "service_unavailable", "No se pudo verificar la operación. Contacta atención humana.",
                                    "Não foi possível verificar a operação. Contate o atendimento humano.")
                else:
                    result = escalate("tool_failure", "general", "P2" if s.get("intent") in {"not_me", "emergency"} or name == "fraud_agent" else "P3")
            # Interrupt exceptions intentionally propagate to LangGraph.
            result.setdefault("turns", s.get("turns", 1))
            result["trace"] = s.get("trace", []) + [{"node": name, "phase": s.get("phase"),
                "next": result["route"], "at": services.now().isoformat()}]
            return result
        return node

    routes = {name: name for name in NODES} | {"end": END}
    for name, function in NODES.items():
        builder.add_node(name, wrap(name, function))
        builder.add_conditional_edges(name, lambda s: s["route"], routes)
    builder.add_edge(START, "validator_agent")
    return builder.compile(checkpointer=checkpointer)
