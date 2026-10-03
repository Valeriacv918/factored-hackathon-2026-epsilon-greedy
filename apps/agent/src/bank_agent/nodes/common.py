from decimal import Decimal, InvalidOperation

from langgraph.types import interrupt

from bank_agent.clients.contracts import ServiceFailure, SessionExpired


class HandoffRequested(Exception):
    def __init__(self, reason="requested_human"):
        self.reason = reason


def go(route, phase="start", **updates):
    return {"route": route, "phase": phase, **updates}


def escalate(reason, queue="general", priority="P3"):
    return go("escalation", reason=reason, queue=queue, priority=priority)


def require_session(s, services):
    customer = services.validate_session(s["session_ref"])
    if not customer or (s.get("customer_id") and customer != s["customer_id"]):
        raise SessionExpired()
    return customer


def say(s, es, pt, en):
    """Pick the reply in the conversation language; Spanish until one is known."""
    return {"es": es, "pt": pt, "en": en}.get(s.get("language"), es)


def ask(s, services, kind, options, es, pt, en, **details):
    # No mutations before interrupt: LangGraph restarts this node on resume.
    if s.get("customer_id") and "human" not in options:
        options = [*options, "human"]
    reply = interrupt({"kind": kind, "language": s.get("language"),
                       "message": say(s, es, pt, en),
                       "options": options, **details})
    if s.get("customer_id"):
        require_session(s, services)  # Check again after the human wait.
    if not isinstance(reply, dict) or set(reply) != {"choice"}:
        raise ValueError("Resume requires exactly {'choice': <button value>}.")
    if reply["choice"] == "human" and s.get("customer_id"):
        raise HandoffRequested()
    if reply["choice"] not in options:
        raise ValueError("Choice is not one of the offered buttons.")
    s["turns"] = s.get("turns", 1) + 1
    return reply["choice"]


def tool(s, services, name, **arguments):
    require_session(s, services)
    for attempt in range(2):
        try:
            return services.tool(name, session_ref=s["session_ref"],
                                 customer_id=s["customer_id"], arguments=arguments)
        except ServiceFailure:
            if attempt:
                raise


def verified_action(s, services, action, read, target, **arguments):
    key = f"{s['conversation_id']}:{action}:{target}"
    receipt = tool(s, services, action, idempotency_key=key, **arguments)
    if not receipt.get("id"):
        raise ServiceFailure("Missing action receipt")
    record = tool(s, services, read, id=receipt["id"])
    if record.get("id") != receipt["id"] or record.get("verified") is not True:
        raise ServiceFailure("Action could not be verified")
    return record


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def finish(s, outcome, es, pt, en):
    return go("end", outcome=outcome, response=say(s, es, pt, en))


def block(s, services, route):
    """A separate checkpointed phase; confirmation occurs before mutation."""
    card = s["card_id"]
    result = tool(s, services, "get_card", card_id=card)
    if result.get("id") != card or result.get("customer_id") != s["customer_id"]:
        raise ServiceFailure("Card ownership mismatch")
    if result.get("status") != "Blocked":
        answer = ask(s, services, "confirm_block", ["yes", "no"],
                     "¿Confirmas el bloqueo de esta tarjeta?", "Confirma o bloqueio deste cartão?",
                     "Do you confirm blocking this card?", card_id=card)
        if answer == "no":
            return escalate("block_declined", "fraud", "P1")
        result = verified_action(s, services, "block_card", "read_block", card, card_id=card)
        if result.get("card_id") != card or result.get("status") != "Blocked":
            raise ServiceFailure("Unexpected block result")
    times = {**s.get("block_verified_at", {}), card: services.now().isoformat()}
    return go(route, "after_block", blocked_cards=list(dict.fromkeys(s["blocked_cards"] + [card])),
              block_verified_at=times)


def file_case(s, services, route):
    tx = s["transaction"]
    answer = ask(s, services, "confirm_dispute", ["yes", "no"],
                 "¿Confirmas registrar la disputa?", "Confirma o registro da contestação?",
                 "Do you confirm filing the dispute?",
                 transaction={k: tx[k] for k in ("id", "amount", "currency", "date")})
    if answer == "no":
        return go("fraud", "more") if route == "fraud" else finish(s, "cancelled", "No se registró una disputa.", "Nenhuma contestação foi registrada.",
                                                                   "No dispute was filed.")
    record = verified_action(s, services, "file_dispute", "read_dispute", tx["id"],
                             transaction_id=tx["id"])
    if record.get("transaction_id") != tx["id"] or record.get("customer_id") != s["customer_id"]:
        raise ServiceFailure("Unexpected dispute result")
    cases = list(dict.fromkeys(s["case_ids"] + [record["id"]]))
    updates = {"case_ids": cases, "case_verified_at": {
        **s["case_verified_at"], record["id"]: services.now().isoformat()}}
    if route == "fraud":
        return go("fraud", "more", **updates)
    return {**finish(s, "dispute_filed", f"Disputa registrada: {record['id']}.",
                     f"Contestação registrada: {record['id']}.",
                     f"Dispute filed: {record['id']}."), **updates}
