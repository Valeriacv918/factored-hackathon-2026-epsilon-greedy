from bank_agent.graphs.policy import decide
from bank_agent.nodes.common import ask, escalate, file_case, finish, go, tool

# Status -> (rule, es, pt). STATE_MACHINE2 "Explanations".
EXPLANATIONS = {
    "Pending": ("EXP-002", "La transacción figura pendiente.", "A transação consta como pendente."),
    "Reversed": ("EXP-003", "La transacción figura reversada.", "A transação consta como revertida."),
    "Declined": ("EXP-006", "La transacción figura rechazada.", "A transação consta como recusada."),
}


def run(s, services, policy):
    tx = s["transaction"]
    if s["phase"] == "file":
        return file_case(s, services, "charge_error")
    if tx["status"] in EXPLANATIONS:
        rule, es, pt = EXPLANATIONS[tx["status"]]
        answer = ask(s, services, "explanation", ["understood", "still_wrong"], es, pt, explanation_rule=rule)
        if answer == "still_wrong":
            return {**escalate("explanation_rejected", "disputes", "P3"), "explanation_rule": rule}
        return {**finish(s, "explained", es, pt), "explanation_rule": rule}
    if tx["status"] != "Approved":
        return escalate("unknown_status", "disputes")
    context = tool(s, services, "dispute_context", transaction_id=tx["id"])
    decision, rule = decide(tx, context, services.now(), policy)
    if decision == "duplicate":
        case = context["existing_case_id"]
        return {**finish(s, "existing_case", f"Ya existe el caso {case}.", f"Já existe o caso {case}."),
                "policy_rule": rule}
    if decision == "deny":
        return {**finish(s, "outside_window", f"El cargo está fuera del plazo de la política de demostración ({policy.window_days} días).",
                         f"A transação está fora do prazo da política de demonstração ({policy.window_days} dias)."),
                "policy_rule": rule}
    if decision == "escalate":
        return {**escalate(rule, "disputes", "P3"), "policy_rule": rule}
    return go("charge_error", "file", policy_rule=rule)