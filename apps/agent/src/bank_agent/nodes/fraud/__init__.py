from bank_agent.graphs.policy import decide
from bank_agent.nodes.common import ask, block, escalate, file_case, finish, go, number, tool


def run(s, services, policy):
    phase, tx = s["phase"], s["transaction"]
    if phase == "start":
        if not tx.get("card_id"):
            return escalate("no_blockable_card", "fraud", "P2")
        return go("fraud", "block", card_id=tx["card_id"])
    if phase == "block":
        return block(s, services, "fraud")
    if phase == "after_block":
        status = tx["status"]
        if status == "Pending":
            return escalate("pending_fraud", "fraud", "P2")
        if status in {"Reversed", "Declined"}:
            return go("fraud", "more")
        if status != "Approved":
            return escalate("unknown_status", "fraud", "P2")
        context = tool(s, services, "dispute_context", transaction_id=tx["id"])
        decision, rule = decide(tx, context, services.now(), policy, fraud=True)
        if decision == "duplicate":
            return go("fraud", "more", case_ids=list(dict.fromkeys(s["case_ids"] + [context["existing_case_id"]])))
        if decision == "escalate":
            return escalate(rule, "fraud", "P2")
        return go("fraud", "file")
    if phase == "file":
        return file_case(s, services, "fraud")
    if phase == "more":
        answer = ask(s, services, "more_charges", ["yes", "no"],
                     "¿Hay otro cargo que no reconoces?", "Há outra transação que você não reconhece?")
        if answer == "yes":
            if len(s["denied_transactions"]) >= policy.max_charges:
                return escalate("charge_limit", "fraud", "P1")
            return go("understanding", "clarify", intent="not_me", slots={})
        return go("fraud", "risk")
    transactions = {t["id"]: t for t in s.get("risk_transactions", []) + [tx]}.values()
    scores = [number(t.get("fraud_score")) for t in transactions]
    amounts = [number(t.get("amount_usd")) for t in transactions]
    if any(score is not None and score > policy.fraud_score for score in scores) or len(s["denied_transactions"]) >= 2:
        return escalate("DSP-013", "fraud", "P1")
    if any(value is None for value in scores + amounts):
        return escalate("missing_risk_data", "fraud", "P2")
    if any(amount > policy.high_amount_usd for amount in amounts):
        return escalate("DSP-013", "fraud", "P2")
    ids = ", ".join(s["case_ids"]) or "—"
    return finish(s, "fraud_intake_complete", f"Bloqueo verificado. Casos registrados o existentes: {ids}.",
                  f"Bloqueio verificado. Casos registrados ou existentes: {ids}.")
