"""Live agent -> MCP -> BigQuery checks. Opt-in: run with `pytest -m integration`.

Starts the real MCP server in its own env (uv run --project apps/mcp-server), as
production does, and reads bank_curated with the caller's ADC. Read-only.
The session is the `dev` entry of DEV_SESSIONS (environment or repository .env),
a token minted with `bank-mcp-token CUSTOMER_ID`, the same one
`run_disputes.py --session dev` uses; SCENARIO_NOW sets the reference date
(default 2026-06-18). The server needs SESSION_SIGNING_KEY in the same .env.
With SANDBOX_SCENARIO_ID set, the sandbox read tools are checked too. Nothing here
writes: block/dispute/handoff writes add rows to the shared scenario.
"""
import datetime as dt
import json
import os
import shutil

import pytest
from dotenv import dotenv_values

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.clients.mcp_client import McpToolClient
from bank_agent.clients.mcp_services import REPO_ROOT
from bank_agent.clients.sessions import StaticSessions
from bank_agent.graphs.policy import Policy

pytestmark = pytest.mark.integration

# Read .env without exporting it, so default (non-integration) runs are unaffected.
ENV = {**dotenv_values(REPO_ROOT / ".env"), **os.environ}
try:
    GRANT = StaticSessions.from_string(ENV.get("DEV_SESSIONS") or "").resolve("dev")
except ValueError:
    GRANT = None
if not GRANT or not shutil.which("uv"):
    pytest.skip("Set DEV_SESSIONS=dev=<token from bank-mcp-token> and install uv to run live MCP tests.",
                allow_module_level=True)
CUSTOMER, TOKEN = GRANT.customer_id, GRANT.token

REFERENCE_DATE = (dt.datetime.fromisoformat(ENV["SCENARIO_NOW"]).date()
                  if ENV.get("SCENARIO_NOW") else dt.date(2026, 6, 18))
CONTRACTS = REPO_ROOT / "contracts" / "mcp"
WINDOW_DAYS = Policy().window_days
SANDBOX = bool(ENV.get("SANDBOX_SCENARIO_ID"))


def output_fields(tool, definition):
    schema = json.loads((CONTRACTS / f"{tool}.json").read_text(encoding="utf-8"))["output_schema"]
    return set(schema["$defs"][definition]["properties"])


@pytest.fixture(scope="module")
def client():
    # First start may sync the server env; allow for it.
    with McpToolClient(command="uv", args=["run", "--project", str(REPO_ROOT / "apps" / "mcp-server"), "bank-mcp"],
                       cwd=REPO_ROOT, timeout_s=60) as c:
        yield c


@pytest.fixture(scope="module")
def cards(client):
    cards = client.call("list_cards", {"session_token": TOKEN})["cards"]
    if not cards:
        pytest.skip(f"Customer {CUSTOMER} has no cards in bank_curated.")
    return cards


def test_list_cards_returns_only_the_customers_cards(cards):
    assert all(card["customer_id"] == CUSTOMER for card in cards)
    assert set(cards[0]) == output_fields("list_cards", "Card")


def test_get_card_matches_list(client, cards):
    card = client.call("get_card", {"session_token": TOKEN, "card_id": cards[0]["id"]})
    assert card == cards[0]


@pytest.fixture(scope="module")
def transactions(client):
    return client.call("find_transactions", {"session_token": TOKEN, "reference_date": REFERENCE_DATE.isoformat(),
                                             "window_days": WINDOW_DAYS, "limit": 3})


def test_find_transactions_matches_contract(transactions):
    result = transactions
    assert isinstance(result["has_more"], bool)
    assert len(result["transactions"]) <= 3
    for tx in result["transactions"]:
        assert tx["customer_id"] == CUSTOMER
        assert set(tx) == output_fields("find_transactions", "Transaction")


def test_customer_id_argument_is_ignored(client, cards):
    # The server takes the customer only from the signed token; an extra customer_id is dropped.
    other = client.call("list_cards", {"session_token": TOKEN, "customer_id": "CLI-SOMEONE-ELSE"})["cards"]
    assert other == cards


def test_forged_token_is_rejected(client, cards):
    payload, _ = TOKEN.split(".")
    with pytest.raises(SessionExpired):
        client.call("get_card", {"session_token": f"{payload}.forged", "card_id": cards[0]["id"]})


def test_wrong_identity_is_refused_without_data(client):
    result = client.call("verify_identity", {"document_number": "0000000000", "date_of_birth": "1900-01-01",
                                             "product_number": "00000000"})
    assert result["status"] == "failed" and result["attempts_left"] >= 0
    assert result["customer_id"] is None and result["session_token"] is None and result["product_numbers"] == []


@pytest.mark.skipif(not SANDBOX, reason="SANDBOX_SCENARIO_ID not set")
def test_dispute_context_for_an_own_transaction(client, transactions):
    if not transactions["transactions"]:
        pytest.skip(f"Customer {CUSTOMER} has no transactions in the window.")
    tx = transactions["transactions"][0]["id"]
    context = client.call("dispute_context", {"session_token": TOKEN, "transaction_id": tx})
    assert set(context) == {"existing_case_id", "recent_dispute_count"}
    assert context["recent_dispute_count"] >= 0


@pytest.mark.skipif(not SANDBOX, reason="SANDBOX_SCENARIO_ID not set")
@pytest.mark.parametrize("tool", ["read_block", "read_dispute", "read_handoff", "read_notification"])
def test_unknown_receipt_is_not_verified(client, tool):
    with pytest.raises(ServiceFailure):
        client.call(tool, {"session_token": TOKEN, "id": "NO-SUCH-RECEIPT"})
