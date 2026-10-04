from bank_agent.nodes.common import finish, go, tool, verified_action
from bank_agent.clients.contracts import ServiceFailure
from bank_agent.nodes.escalation.handoff import build_facts, write_narrative




def run(s, services, policy):
    if s["phase"] == "start":
        packet = {
            "reason": s["reason"], "queue": s["queue"], "priority": s["priority"],
            "customer_quote": s["message"], "language": s["language"],
            "transaction_ids": [t["id"] for t in s.get("risk_transactions", [])],
            "case_ids": s["case_ids"], "blocked_cards": s["blocked_cards"],
            "suspended_accounts": s["suspended_accounts"],
            "not_done": [s["reason"]], "next_steps": ["human_review"],
            "policy_version": policy.version,
        }
        if s.get("transaction"):
            packet["transaction_ids"] = list(dict.fromkeys(packet["transaction_ids"] + [s["transaction"]["id"]]))
        packet.update({k: s[k] for k in ("policy_rule", "explanation_rule") if s.get(k)})
        # WRITE_NARRATIVE + claim check: the LLM sees only verified facts, never the customer's text.
        facts = build_facts(s, policy)
        packet["narrative"], packet["narrative_source"], packet["claim_issues"] = write_narrative(
            services, facts, s.get("language", "es"))
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
