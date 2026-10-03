"""Six-node graph. Each phase commits separately before any next human wait."""
from copy import deepcopy

from langgraph.graph import END, START, StateGraph

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.graphs.policy import Policy
from bank_agent.graphs.state import ConversationState
from bank_agent.nodes import charge_error, escalation, fraud, lost_card, security_language, understanding
from bank_agent.nodes.common import HandoffRequested, escalate, finish, require_session

NODES = {
    "security_language": security_language.run,
    "understanding": understanding.run,
    "lost_card": lost_card.run,
    "fraud": fraud.run,
    "charge_error": charge_error.run,
    "escalation": escalation.run,
}


def build_graph(services, *, checkpointer, policy=None):
    """Require an explicit saver; InMemorySaver is suitable only for local tests.

    The hosting service must bind thread_id and session_ref to the authenticated
    principal, restrict initial input to initial_state(), and only allow validated
    Command(resume=...) payloads thereafter. Do not expose graph.invoke directly.
    """
    policy = policy or Policy()
    builder = StateGraph(ConversationState)

    def wrap(name, function):
        def node(state):
            s = deepcopy(state)
            try:
                if name != "security_language":
                    require_session(s, services)
                if name not in {"security_language", "escalation"} and s["turns"] >= policy.max_turns:
                    result = escalate("turn_limit", "general", "P2" if s.get("intent") == "not_me" else "P3")
                else:
                    result = function(s, services, policy)
            except SessionExpired:
                result = finish(s, "authentication_required", "Inicia sesión para continuar.", "Entre na sua conta para continuar.",
                                "Sign in to continue.")
            except HandoffRequested as exc:
                result = escalate(exc.reason, "general", "P2" if s.get("intent") in {"not_me", "card_emergency"} else "P3")
            except ServiceFailure:
                if name in {"escalation", "security_language"}:
                    result = finish(s, "service_unavailable", "No se pudo verificar la operación. Contacta atención humana.",
                                    "Não foi possível verificar a operação. Contate o atendimento humano.",
                                    "The operation could not be verified. Please contact a human agent.")
                else:
                    result = escalate("tool_failure", "general", "P2" if s.get("intent") in {"not_me", "card_emergency"} or name == "fraud" else "P3")
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
    builder.add_edge(START, "security_language")
    return builder.compile(checkpointer=checkpointer)
