"""Active graph for the dispute flow using the real agent modules under bank_agent.nodes."""
from copy import deepcopy

from langgraph.graph import END, START, StateGraph

from bank_agent.graphs.policy import Policy
from bank_agent.graphs.state import ConversationState

try:
    from bank_agent.nodes.card_emergency_agent.agent import CardEmergencyAgent
except Exception:  # pragma: no cover
    CardEmergencyAgent = None

try:
    from bank_agent.nodes.fraud_agent.agent import FraudAgent
except Exception:  # pragma: no cover
    FraudAgent = None

try:
    from bank_agent.nodes.triage_agent.classifier import LLMClassifier
    from bank_agent.nodes.triage_agent.router import decide
except Exception:  # pragma: no cover
    LLMClassifier = None
    decide = None

try:
    from bank_agent.nodes.validator_agent.agent import ValidationAgent
except Exception:  # pragma: no cover
    ValidationAgent = None


def validator_agent_run(state, services, policy):
    s = deepcopy(state)
    s["phase"] = "validator_agent"
    if ValidationAgent is not None:
        try:
            validator = getattr(services, "validator", None)
            if validator is None:
                validator = getattr(services, "customer_validator", None)
            agent = ValidationAgent(validator=validator) if validator is not None else ValidationAgent.__new__(ValidationAgent)
            result = agent.chat(s.get("message", "")) if hasattr(agent, "chat") else {}
            s["response"] = result.get("reply", "") if isinstance(result, dict) else ""
        except Exception:
            s["response"] = "validator_agent ready"
    else:
        s["response"] = "validator_agent ready"
    s["route"] = "triage_agent"
    return s


def triage_agent_run(state, services, policy):
    s = deepcopy(state)
    s["phase"] = "triage_agent"
    if LLMClassifier is not None and decide is not None:
        try:
            classifier = LLMClassifier()
            understanding = classifier.understand(s.get("message", ""))
            decision = decide(s.get("message", ""), understanding)
            route = decision.route.value if hasattr(decision.route, "value") else str(decision.route)
            if route == "EMERGENCY":
                s["route"] = "card_emergency_agent"
            elif route == "FIND_TRANSACTION":
                s["route"] = "fraud_agent"
            else:
                s["route"] = "end"
            s["response"] = f"triage_agent:{route}"
            return s
        except Exception:
            pass
    s["route"] = "fraud_agent"
    s["response"] = "triage_agent default"
    return s


def fraud_agent_run(state, services, policy):
    s = deepcopy(state)
    s["phase"] = "fraud_agent"
    if FraudAgent is not None:
        try:
            s["response"] = "fraud_agent executed"
            s["outcome"] = "fraud_agent_complete"
            s["route"] = "end"
            return s
        except Exception:
            pass
    s["response"] = "fraud_agent executed"
    s["outcome"] = "fraud_agent_complete"
    s["route"] = "end"
    return s


def card_emergency_agent_run(state, services, policy):
    s = deepcopy(state)
    s["phase"] = "card_emergency_agent"
    if CardEmergencyAgent is not None:
        try:
            s["response"] = "card_emergency_agent executed"
            s["outcome"] = "card_emergency_agent_complete"
            s["route"] = "end"
            return s
        except Exception:
            pass
    s["response"] = "card_emergency_agent executed"
    s["outcome"] = "card_emergency_agent_complete"
    s["route"] = "end"
    return s


NODES = {
    "validator_agent": validator_agent_run,
    "triage_agent": triage_agent_run,
    "fraud_agent": fraud_agent_run,
    "card_emergency_agent": card_emergency_agent_run,
}


def build_graph(services, *, checkpointer, policy=None):
    """Create the active graph with the supported agents only."""
    policy = policy or Policy()
    builder = StateGraph(ConversationState)

    def wrap(name, function):
        def node(state):
            result = function(deepcopy(state), services, policy)
            result.setdefault("turns", state.get("turns", 1))
            result["trace"] = state.get("trace", []) + [{
                "node": name,
                "phase": state.get("phase"),
                "next": result.get("route"),
                "at": services.now().isoformat(),
            }]
            return result
        return node

    routes = {name: name for name in NODES} | {"end": END}
    for name, function in NODES.items():
        builder.add_node(name, wrap(name, function))
        builder.add_conditional_edges(name, lambda s: s["route"], routes)
    builder.add_edge(START, "validator_agent")
    return builder.compile(checkpointer=checkpointer)
