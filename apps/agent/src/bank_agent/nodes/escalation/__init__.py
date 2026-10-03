from bank_agent.nodes.common import finish, go, tool, verified_action
from bank_agent.clients.contracts import ServiceFailure


def run(s, services, policy):
    if s["phase"] == "start":
        packet = {
            "reason": s["reason"], "queue": s["queue"], "priority": s["priority"],
            "customer_quote": s["message"], "language": s["language"],
            "transaction_ids": [t["id"] for t in s.get("risk_transactions", [])],
            "case_ids": s["case_ids"], "blocked_cards": s["blocked_cards"],
            "not_done": [s["reason"]], "next_steps": ["human_review"],
            "policy_version": policy.version,
        }
        if s.get("transaction"):
            packet["transaction_ids"] = list(dict.fromkeys(packet["transaction_ids"] + [s["transaction"]["id"]]))
        # Factual template until a narrative model and claim checker are connected.
        packet["narrative"] = f"{packet['reason']}; cases={packet['case_ids']}; blocked={packet['blocked_cards']}"
        return go("escalation", "ticket", handoff=packet)
    if s["phase"] == "ticket":
        record = verified_action(s, services, "create_handoff", "read_handoff", "handoff", packet=s["handoff"])
        if record.get("customer_id") != s["customer_id"]:
            raise ServiceFailure("Handoff ownership mismatch")
        return go("escalation", "notify", ticket_id=record["id"])
    receipt = verified_action(s, services, "notify_employee", "read_notification", s["ticket_id"], ticket_id=s["ticket_id"])
    if receipt.get("ticket_id") != s["ticket_id"]:
        raise ServiceFailure("Notification mismatch")
    ticket = s["ticket_id"]
    return {**finish(s, "escalated", f"Caso enviado a atención humana. Ticket: {ticket}.",
                     f"Caso encaminhado ao atendimento humano. Ticket: {ticket}."),
            "handoff_at": services.now().isoformat()}
