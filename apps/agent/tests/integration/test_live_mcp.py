"""Live agent -> MCP -> BigQuery checks. Opt-in: run with `pytest -m integration`.

Starts the real MCP server in its own env (uv run --project apps/mcp-server), as
production does, and reads bank_curated with the caller's ADC. Read-only.
The customer is the `dev` entry of DEV_SESSIONS (environment or repository .env),
the same one `run_disputes.py --session dev` uses; SCENARIO_NOW sets the
reference date (default 2026-06-18).
"""
import datetime as dt
import json
import os
import shutil

import pytest
from dotenv import dotenv_values

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.clients.mcp_client import McpToolClient
from bank_agent.clients.mcp_services import REPO_ROOT
from bank_agent.clients.sessions import StaticSessions

pytestmark = pytest.mark.integration

# Read .env without exporting it, so default (non-integration) runs are unaffected.
ENV = {**dotenv_values(REPO_ROOT / ".env"), **os.environ}
CUSTOMER = StaticSessions.from_string(ENV.get("DEV_SESSIONS") or "").resolve("dev")
if not CUSTOMER or not shutil.which("uv"):
    pytest.skip("Set DEV_SESSIONS=dev=<customer_id> and install uv to run live MCP tests.", allow_module_level=True)

REFERENCE_DATE = (dt.datetime.fromisoformat(ENV["SCENARIO_NOW"]).date()
                  if ENV.get("SCENARIO_NOW") else dt.date(2026, 6, 18))
CONTRACTS = REPO_ROOT / "contracts" / "mcp"


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
    cards = client.call("list_cards", {"customer_id": CUSTOMER})["cards"]
    if not cards:
        pytest.skip(f"Customer {CUSTOMER} has no cards in bank_curated.")
    return cards


def test_list_cards_returns_only_the_customers_cards(cards):
    assert all(card["customer_id"] == CUSTOMER for card in cards)
    assert set(cards[0]) == output_fields("list_cards", "Card")


def test_get_card_matches_list(client, cards):
    card = client.call("get_card", {"customer_id": CUSTOMER, "card_id": cards[0]["id"]})
    assert card == cards[0]


def test_find_transactions_matches_contract(client):
    result = client.call("find_transactions", {"customer_id": CUSTOMER,
                                               "reference_date": REFERENCE_DATE.isoformat(), "limit": 3})
    assert isinstance(result["has_more"], bool)
    assert len(result["transactions"]) <= 3
    for tx in result["transactions"]:
        assert tx["customer_id"] == CUSTOMER
        assert set(tx) == output_fields("find_transactions", "Transaction")


def test_card_of_another_customer_is_not_disclosed(client, cards):
    with pytest.raises(ServiceFailure):
        client.call("get_card", {"customer_id": "integration-nobody", "card_id": cards[0]["id"]})
