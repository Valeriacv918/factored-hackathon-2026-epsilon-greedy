"""Only the trusted application initializes this state, never a client JSON body."""

from typing import Any, Literal, TypedDict

Route = Literal["validator_agent", "validation_wait", "request_wait", "triage_agent", "triage_wait", "charge_extract", "charge_find", "charge_details", "charge_select", "charge_error", "charge_save", "fraud_agent", "escalation", "card_emergency_agent", "end"]


class ConversationState(TypedDict, total=False):
    conversation_id: str
    session_ref: str  # Opaque reference; do not checkpoint bearer tokens.
    message: str
    validation_input: str
    validation_status: str | None
    identity_prompts: int  # login form attempts shown (format errors do not count as failed logins)
    authenticated: bool
    triage_choice: str
    triage_route: str
    language: Literal["es", "pt"]
    customer_id: str
    route: Route
    phase: str
    intent: str
    intent_confidence: float
    slots: dict[str, Any]
    charge_input: str
    charge_candidates: list[dict[str, Any]]
    transaction: dict[str, Any]
    card_id: str
    account_id: str
    blocked_cards: list[str]
    skipped_cards: list[str]  
    suspended_accounts: list[str]
    denied_transactions: list[dict[str, Any]]
    risk_transactions: list[dict[str, Any]]
    case_ids: list[str]
    clarification_attempts: int
    turns: int
    reason: str
    policy_rule: str  # DSP-xxx that decided a charge (DSP-004, DSP-005, DSP-100...)
    explanation_result_id: str
    explanation_rule: str
    queue: str
    priority: str
    handoff: dict[str, Any]
    ticket_id: str
    outcome: str
    response: str
    reported_at: str
    block_verified_at: dict[str, str]
    case_verified_at: dict[str, str]
    handoff_at: str
    trace: list[dict[str, Any]]


def initial_state(conversation_id: str, session_ref: str, message: str) -> ConversationState:
    return ConversationState(
        conversation_id=conversation_id, session_ref=session_ref, message=message,
        route="validator_agent", phase="start", turns=1,
        blocked_cards=[], suspended_accounts=[], denied_transactions=[], risk_transactions=[], case_ids=[],
        block_verified_at={}, case_verified_at={}, trace=[], clarification_attempts=0,
    )
