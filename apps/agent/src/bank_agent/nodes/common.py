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


def say(s, es, pt):
    """Pick the reply in the conversation language; Spanish until one is known."""
    return pt if s.get("language") == "pt" else es


def ask(s, services, kind, options, es, pt, **details):
    # No mutations before interrupt: LangGraph restarts this node on resume.
    if s.get("customer_id") and "human" not in options:
        options = [*options, "human"]
    reply = interrupt({"kind": kind, "language": s.get("language"),
                       "message": say(s, es, pt),
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


def finish(s, outcome, es, pt):
    return go("end", outcome=outcome, response=say(s, es, pt))


def block(s, services, route, optional=False):
    """A separate checkpointed phase; confirmation occurs before mutation.

    Not every disputed transaction sits on a card: it may be on a savings or
    checking account. A card gets blocked outright; an account only has its
    ability to transact suspended -- the product itself is never blocked.
    optional=True offers an EXTRA card (e.g. a lost wallet with several cards):
    declining it is the customer's choice, not a risk signal, so it continues
    instead of escalating as block_declined.
    """
    if s.get("account_id"):
        return _suspend_account(s, services, route)
    return _block_card(s, services, route, optional)


def _block_card(s, services, route, optional=False):
    card = s["card_id"]
    result = tool(s, services, "get_card", card_id=card)
    if result.get("id") != card or result.get("customer_id") != s["customer_id"]:
        raise ServiceFailure("Card ownership mismatch")
    if result.get("status") != "Blocked":
        es, pt = (("¿También quieres bloquear esta otra tarjeta?", "Também quer bloquear este outro cartão?")
                  if optional else ("¿Confirmas el bloqueo de esta tarjeta?", "Confirma o bloqueio deste cartão?"))
        answer = ask(s, services, "confirm_block", ["yes", "no"], es, pt, card_id=card, last4=result.get("last4"))
        if answer == "no":
            if optional:
                return go(route, "after_block", skipped_cards=list(dict.fromkeys(s.get("skipped_cards", []) + [card])))
            return escalate("block_declined", "fraud", "P1")
        result = verified_action(s, services, "block_card", "read_block", card, card_id=card)
        if result.get("card_id") != card or result.get("status") != "Blocked":
            raise ServiceFailure("Unexpected block result")
    times = {**s.get("block_verified_at", {}), card: services.now().isoformat()}
    return go(route, "after_block", blocked_cards=list(dict.fromkeys(s["blocked_cards"] + [card])),
              block_verified_at=times)

def _suspend_account(s, services, route):
    account = s["account_id"]
    result = tool(s, services, "get_account", account_id=account)
    if result.get("id") != account or result.get("customer_id") != s["customer_id"]:
        raise ServiceFailure("Account ownership mismatch")
    if result.get("status") != "TransactionsSuspended":
        answer = ask(s, services, "confirm_suspend", ["yes", "no"],
                     "¿Confirmas suspender las transacciones de esta cuenta?",
                     "Confirma a suspensão das transações desta conta?",
                     account_id=account)
        if answer == "no":
            return escalate("block_declined", "fraud", "P1")
        result = verified_action(s, services, "suspend_account_transactions", "read_suspension",
                                 account, account_id=account)
        if result.get("account_id") != account or result.get("status") != "TransactionsSuspended":
            raise ServiceFailure("Unexpected suspension result")
    times = {**s.get("block_verified_at", {}), account: services.now().isoformat()}
    return go(route, "after_block",
              suspended_accounts=list(dict.fromkeys(s["suspended_accounts"] + [account])),
              block_verified_at=times)


def file_case(s, services, route):
    tx = s["transaction"]
    answer = ask(s, services, "confirm_dispute", ["yes", "no"],
                 "¿Confirmas registrar la disputa?", "Confirma o registro da contestação?",
                 transaction={k: tx[k] for k in ("id", "amount", "currency", "date")})
    if answer == "no":
        return go("fraud_agent", "more") if route == "fraud_agent" else finish(s, "cancelled", "No se registró una disputa.", "Nenhuma contestação foi registrada.")
    record = verified_action(s, services, "file_dispute", "read_dispute", tx["id"],
                             transaction_id=tx["id"])
    if record.get("transaction_id") != tx["id"] or record.get("customer_id") != s["customer_id"]:
        raise ServiceFailure("Unexpected dispute result")
    cases = list(dict.fromkeys(s["case_ids"] + [record["id"]]))
    updates = {"case_ids": cases, "case_verified_at": {
        **s["case_verified_at"], record["id"]: services.now().isoformat()}}
    if route == "fraud_agent":
        return go("fraud_agent", "more", **updates)
    return {**finish(s, "dispute_filed", f"Disputa registrada: {record['id']}.",
                     f"Contestação registrada: {record['id']}."), **updates}
