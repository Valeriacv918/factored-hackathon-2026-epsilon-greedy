from bank_agent.clients.contracts import ServiceFailure
from bank_agent.nodes.common import ask, block, escalate, go, tool


def run(s, services, policy):
    phase = s["phase"]
    if phase == "start":
        cards = tool(s, services, "list_cards").get("cards", [])
        if any(c.get("customer_id") != s["customer_id"] for c in cards):
            raise ServiceFailure("Cross-customer card rejected")
        cards = [c for c in cards if c.get("status") in {"Active", "Blocked"}]
        if not cards:
            return escalate("no_blockable_card", "cards", "P2")
        card = cards[0]["id"] if len(cards) == 1 else ask(
            s, services, "select_card", [c["id"] for c in cards],
            "Selecciona la tarjeta.", "Selecione o cartão.",
            cards=[{"id": c["id"], "last4": c["last4"]} for c in cards])
        return go("lost_card", "block", card_id=card)
    if phase == "block":
        return block(s, services, "lost_card")
    answer = ask(s, services, "unrecognized_charge", ["yes", "no"],
                 "¿Hay algún cargo que no reconoces?", "Há alguma transação que você não reconhece?")
    if answer == "yes":
        return go("understanding", "clarify", intent="not_me", slots={})
    return escalate("card_replacement", "cards", "P3")
