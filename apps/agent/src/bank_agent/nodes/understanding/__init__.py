from langgraph.types import interrupt

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.nodes.common import ask, escalate, finish, go, number, require_session, say, tool
from bank_agent.nodes.triage_agent.router import decide
from bank_agent.nodes.triage_agent.schemas import Route, Understanding

INTENTS = {"not_me", "charge_error", "emergency", "other"}


SEARCH_FIELDS = {"merchant", "amount", "currency", "date", "date_from", "date_to"}

def search_slots(slots):
    """Triage slots -> find_transactions slots (contracts/mcp/find_transactions.json).
    Slots are already normalized by triage_agent.schemas.Slots; product_hint is not a search field."""
    return slots.model_dump(mode="json", exclude_none=True, include=SEARCH_FIELDS)

def run(s, services, policy):
    phase = s.get("phase", "start")
    if phase == "start":
        u = services.triage_understand(s["message"])
        u = u if isinstance(u, Understanding) else Understanding.model_validate(u)
        decision = decide(s["message"], u)
        intent = decision.intent.value if decision.intent else "other"
        common = {"slots": search_slots(u.slots), "intent_confidence": u.confidence}
        if decision.route == Route.ESCALATION:
            return {**escalate("requested_human", "general", "P2" if intent in {"not_me", "emergency"} else "P3"),
                    "intent": intent, **common}
        if decision.route == Route.EMERGENCY:
            return go("card_emergency_agent", intent="emergency", **common)
        if decision.route == Route.CLARIFY_INTENT:
            return go("understanding", "triage", intent="other", reason="clarify_intent", **common)
        if decision.route == Route.OUT_OF_SCOPE:
            return go("understanding", "out_of_scope", intent="other", **common)
        return go("understanding", "find", intent=intent, **common)
    if phase == "triage":
        intent = s["intent"]
        if s.get("reason") == "clarify_intent":
            intent = ask(s, services, "intent", sorted(INTENTS),
                         "¿Cargo desconocido, error en un cargo o tarjeta perdida?",
                         "Compra não reconhecida, erro na cobrança ou cartão perdido?")
        if intent == "emergency":
            return go("card_emergency_agent", intent=intent)
        if intent == "other":
            return go("understanding", "out_of_scope", intent=intent)
        return go("understanding", "find", intent=intent)
    if phase == "out_of_scope":
        # The classifier said "other". Offer the intents as buttons so the customer can correct
        # a misclassification instead of being stuck. ask() adds "human" (HandoffRequested).
        choice = ask(s, services, "out_of_scope", ["not_me", "charge_error", "emergency", "close"],
                     "Atiendo cargos que no reconoces, cobros equivocados y emergencias de tus productos "
                     "(tarjeta perdida o robada). ¿Es alguno de estos? También puedes solicitar una persona.",
                     "Atendo cobranças que você não reconhece, cobranças erradas e emergências dos seus produtos "
                     "(cartão perdido ou roubado). É algum destes? Você também pode solicitar uma pessoa.")
        if choice == "close":
            return finish(s, "out_of_scope", "Para otros temas, usa los canales de atención del banco.",
                          "Para outros assuntos, use os canais de atendimento do banco.")
        return go("understanding", "triage", intent=choice, reason="")   # route as if the classifier had said it
    if phase == "clarify":
        reply = interrupt({"kind": "transaction_details", "language": s["language"],
                           "message": say(s, "Indica fecha, monto o comercio.",
                                          "Informe data, valor ou estabelecimento."), "fields": ["text"]})
        require_session(s, services)
        if not isinstance(reply, dict) or set(reply) != {"text"} or not isinstance(reply["text"], str) or not reply["text"].strip():
            raise ValueError("Expected {'text': <nonempty clarification>}.")
        parsed = services.understand(reply["text"], s["language"])
        if parsed.get("wants_human") is True:
            return escalate("requested_human")
        if parsed.get("intent") == "emergency":
            return go("card_emergency_agent", intent="emergency")
        if not isinstance(parsed.get("slots", {}), dict):
            raise ServiceFailure("Invalid clarification schema")
        return go("understanding", "find", slots={**s.get("slots", {}), **parsed.get("slots", {})},
                  turns=s["turns"] + 1, clarification_attempts=s["clarification_attempts"] + 1)

    # Ownership is checked by the service before returning any candidates.
    result = tool(s, services, "find_transactions", slots=s.get("slots", {}), limit=3,
                  window_days=policy.window_days)
    candidates = result.get("transactions", [])
    if any(t.get("customer_id") != s["customer_id"] for t in candidates):
        raise ServiceFailure("Cross-customer result rejected")
    if not candidates or result.get("has_more"):
        if s["clarification_attempts"] >= policy.max_clarifications:
            return escalate("transaction_unresolved")
        return go("understanding", "clarify")
    if len(candidates) > 1:
        selected = ask(s, services, "select_transaction", [t["id"] for t in candidates],
                       "Selecciona el cargo.", "Selecione a transação.",
                       transactions=[{k: t[k] for k in ("id", "amount", "currency", "date")} for t in candidates])
        tx = next(t for t in candidates if t["id"] == selected)
    else:
        tx = candidates[0]
    score = number(tx.get("fraud_score"))
    if s["intent"] != "not_me" and score is None:
        return escalate("missing_fraud_score")
    fraud = s["intent"] == "not_me" or score > policy.fraud_score
    denied = s["denied_transactions"]
    if s["intent"] == "not_me" and tx["id"] not in {t["id"] for t in denied}:
        denied = denied + [tx]
    risks = {t["id"]: t for t in s.get("risk_transactions", [])}
    if fraud:
        risks[tx["id"]] = tx
    return go("fraud_agent" if fraud else "charge_error", transaction=tx,
              denied_transactions=denied, risk_transactions=list(risks.values()), clarification_attempts=0)
