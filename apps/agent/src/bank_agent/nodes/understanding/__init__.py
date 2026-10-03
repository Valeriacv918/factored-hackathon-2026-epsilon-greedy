from langgraph.types import interrupt

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.nodes.common import ask, escalate, finish, go, number, require_session, tool

INTENTS = {"not_me", "charge_error", "emergency", "other"}


def run(s, services, policy):
    phase = s.get("phase", "start")
    if phase == "start":
        parsed = services.understand(s["message"], s["language"])
        if parsed.get("wants_human") is True:
            return escalate("requested_human")
        intent = parsed.get("intent")
        confidence = number(parsed.get("confidence"))
        if not isinstance(parsed.get("slots", {}), dict):
            raise ServiceFailure("Invalid extraction schema")
        return go("understanding", "triage", intent=intent if intent in INTENTS else "other",
                  slots=parsed.get("slots", {}),
                  reason="clarify_intent" if confidence is None or confidence < policy.intent_confidence else "")
    if phase == "triage":
        intent = s["intent"]
        if s.get("reason") == "clarify_intent":
            intent = ask(s, services, "intent", sorted(INTENTS),
                         "¿Cargo desconocido, error en un cargo o tarjeta perdida?",
                         "Compra não reconhecida, erro na cobrança ou cartão perdido?")
        if intent == "emergency":
            return go("lost_card", intent=intent)
        if intent == "other":
            return go("understanding", "out_of_scope", intent=intent)
        return go("understanding", "find", intent=intent)
    if phase == "out_of_scope":
        answer = ask(s, services, "out_of_scope", ["human", "close"],
                     "Atiendo disputas y emergencias de tarjetas. Puedes solicitar una persona.",
                     "Atendo contestações e emergências de cartões. Você pode solicitar uma pessoa.")
        return finish(s, "out_of_scope", "Solicitud fuera de alcance.", "Solicitação fora do escopo.")
    if phase == "clarify":
        reply = interrupt({"kind": "transaction_details", "language": s["language"],
                           "message": "Indica fecha, monto o comercio." if s["language"] == "es"
                           else "Informe data, valor ou estabelecimento.", "fields": ["text"]})
        require_session(s, services)
        if not isinstance(reply, dict) or set(reply) != {"text"} or not isinstance(reply["text"], str) or not reply["text"].strip():
            raise ValueError("Expected {'text': <nonempty clarification>}.")
        parsed = services.understand(reply["text"], s["language"])
        if parsed.get("wants_human") is True:
            return escalate("requested_human")
        if parsed.get("intent") == "emergency":
            return go("lost_card", intent="emergency")
        if not isinstance(parsed.get("slots", {}), dict):
            raise ServiceFailure("Invalid clarification schema")
        return go("understanding", "find", slots={**s.get("slots", {}), **parsed.get("slots", {})},
                  turns=s["turns"] + 1, clarification_attempts=s["clarification_attempts"] + 1)

    # Ownership is checked by the service before returning any candidates.
    result = tool(s, services, "find_transactions", slots=s.get("slots", {}), limit=3)
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
    return go("fraud" if fraud else "charge_error", transaction=tx,
              denied_transactions=denied, risk_transactions=list(risks.values()), clarification_attempts=0)
