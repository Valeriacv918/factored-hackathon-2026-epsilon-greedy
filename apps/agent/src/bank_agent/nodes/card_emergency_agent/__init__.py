from bank_agent.clients.contracts import ServiceFailure
from bank_agent.nodes.common import ask, block, escalate, go, tool

from .service import CardEmergencyService, EmergencyResult, EmergencyState, EscalationRequest

__all__ = ["CardEmergencyService", "EmergencyResult", "EmergencyState", "EscalationRequest", "run"]


def _cards(s, services):
    cards = tool(s, services, "list_cards").get("cards", [])
    if any(c.get("customer_id") != s["customer_id"] for c in cards):
        raise ServiceFailure("Cross-customer card rejected")
    return cards


def run(s, services, policy):
    """Nodo del grafo (diagrama 2, 'Card emergency'): llamado como
    card_emergency_agent.run por graphs/disputes.py. 100% código, botones
    via ask()/interrupt() -- nunca texto libre interpretado por un LLM.

    Fases: start (SELECT_CARD) -> block (CONFIRM_BLOCK + BLOCK_AND_VERIFY)
    -> after_block: si quedan otras tarjetas activas (p. ej. perdió la billetera),
       ofrece bloquearlas una por una (block_more); rechazar una extra no escala.
    -> ask_charge (ASK_CHARGE).
    """
    phase = s["phase"]
    if phase == "start":
        cards = [c for c in _cards(s, services) if c.get("status") in {"Active", "Blocked"}]
        if not cards:
            return escalate("no_blockable_card", "cards", "P2")
        card = cards[0]["id"] if len(cards) == 1 else ask(
            s, services, "select_card", [c["id"] for c in cards],
            "Selecciona la tarjeta.", "Selecione o cartão.",
            cards=[{"id": c["id"], "last4": c["last4"]} for c in cards])
        return go("card_emergency_agent", "block", card_id=card)
    if phase == "block":
        return block(s, services, "card_emergency_agent")
    if phase == "after_block":
        handled = set(s.get("blocked_cards", [])) | set(s.get("skipped_cards", []))
        others = [c for c in _cards(s, services) if c.get("status") == "Active" and c["id"] not in handled]
        if others:
            return go("card_emergency_agent", "block_more", card_id=others[0]["id"])
        return go("card_emergency_agent", "ask_charge")
    if phase == "block_more":
        return block(s, services, "card_emergency_agent", optional=True)
    answer = ask(s, services, "unrecognized_charge", ["yes", "no"],
                 "¿Hay algún cargo que no reconoces?", "Há alguma transação que você não reconhece?")
    if answer == "yes":
        return go("triage_agent", "clarify", intent="not_me", slots={})
    return escalate("card_replacement", "cards", "P3")