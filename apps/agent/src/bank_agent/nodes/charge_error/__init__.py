from bank_agent.graphs.policy import decide
from bank_agent.nodes.common import ask, escalate, file_case, finish, go, tool

EXPLANATIONS = {
    "Pending": ("La transacción figura pendiente.", "A transação consta como pendente.",
                "The transaction is shown as pending."),
    "Reversed": ("La transacción figura reversada.", "A transação consta como revertida.",
                 "The transaction is shown as reversed."),
    "Declined": ("La transacción figura rechazada.", "A transação consta como recusada.",
                 "The transaction is shown as declined."),
}


def run(s, services, policy):
    tx = s["transaction"]
    if s["phase"] == "file":
        return file_case(s, services, "charge_error")
    if tx["status"] in EXPLANATIONS:
        es, pt, en = EXPLANATIONS[tx["status"]]
        answer = ask(s, services, "explanation", ["understood", "still_wrong"], es, pt, en)
        if answer == "still_wrong":
            return escalate("explanation_rejected", "disputes", "P3")
        return finish(s, "explained", es, pt, en)
    if tx["status"] != "Approved":
        return escalate("unknown_status", "disputes")
    context = tool(s, services, "dispute_context", transaction_id=tx["id"])
    decision, rule = decide(tx, context, services.now(), policy)
    if decision == "duplicate":
        case = context["existing_case_id"]
        return finish(s, "existing_case", f"Ya existe el caso {case}.", f"Já existe o caso {case}.",
                      f"Case {case} already exists.")
    if decision == "deny":
        return finish(s, "outside_window", f"El cargo está fuera del plazo de la política de demostración ({policy.window_days} días).",
                      f"A transação está fora do prazo da política de demonstração ({policy.window_days} dias).",
                      f"The charge is outside the demo policy window ({policy.window_days} days).")
    if decision == "escalate":
        return escalate(rule, "disputes", "P3")
    return go("charge_error", "file")
