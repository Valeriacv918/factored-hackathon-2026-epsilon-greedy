"""BigQuery dry run of every fixed statement. Opt-in: `pytest -m integration`.

The unit tests use a fake gateway, so they never parse the SQL. A dry run compiles each
statement against the real tables (names, types, reserved words, permissions) without
reading or writing data. Runs with your ADC; to check the deployed identity, impersonate
bank-mcp (see the MCP README). Placeholder values: nothing needs to exist.
"""
import datetime as dt

import pytest
from google.cloud import bigquery

from bank_mcp.config.settings import get_settings
from bank_mcp.repositories.bigquery import BigQueryGateway
from bank_mcp.services import sandbox
from bank_mcp.services.search import TransactionSlots, build_find_query
from bank_mcp.sql import queries
from bank_mcp.tools.server import _tables

pytestmark = pytest.mark.integration

NOW = dt.datetime(2026, 6, 17, 12, tzinfo=dt.timezone.utc)
SCOPE = dict(scenario_id="dry-run", customer_id="CLI-DRY")
CARDS = dict(card_types=queries.CARD_TYPES)
HASH = "0" * 64

STATEMENTS = {
    "VERIFY_IDENTITY": dict(document_number="1", date_of_birth="1990-01-01", product_number="1"),
    "SCENARIO_STATE": dict(scenario_id="dry-run"),
    "LIST_CARDS": dict(customer_id="CLI-DRY", **CARDS),
    "GET_CARD": dict(customer_id="CLI-DRY", card_id="P", **CARDS),
    "LIST_CARDS_EFFECTIVE": dict(**SCOPE, products_run_id="r", **CARDS),
    "GET_CARD_EFFECTIVE": dict(**SCOPE, products_run_id="r", card_id="P", **CARDS),
    "INSERT_BLOCK": dict(**SCOPE, idempotency_key="k", card_id="P", block_id="B", request_hash=HASH, **CARDS),
    "FIND_BLOCK_RECEIPT": dict(**SCOPE, idempotency_key="k", card_id="P", products_run_id="r"),
    "READ_BLOCK": dict(**SCOPE, id="B", **CARDS),
    "INSERT_DISPUTE": dict(**SCOPE, idempotency_key="k", transaction_id="T", case_id="C", request_hash=HASH),
    "FIND_DISPUTE_RECEIPT": dict(**SCOPE, idempotency_key="k", transaction_id="T", transactions_run_id="r"),
    "READ_DISPUTE": dict(**SCOPE, id="C"),
    "DISPUTE_CONTEXT": dict(**SCOPE, transaction_id="T", transactions_run_id="r",
                            subcategories=sandbox.DISPUTE_SUBCATEGORIES,
                            history_start=NOW - dt.timedelta(days=90), history_end=NOW),
    "HANDOFF_REFS": dict(**SCOPE, transaction_ids=["T"], case_ids=["C"], card_ids=["P"],
                         transactions_run_id="r", products_run_id="r", **CARDS),
    "INSERT_HANDOFF": dict(**SCOPE, idempotency_key="k", ticket_id="H", request_hash=HASH, packet='{"reason":"x"}'),
    "FIND_HANDOFF_RECEIPT": dict(**SCOPE, idempotency_key="k"),
    "READ_HANDOFF": dict(**SCOPE, id="H"),
    "INSERT_NOTIFICATION": dict(**SCOPE, idempotency_key="k", ticket_id="H", delivery_id="N", request_hash=HASH),
    "FIND_NOTIFICATION_RECEIPT": dict(**SCOPE, idempotency_key="k", ticket_id="H"),
    "READ_NOTIFICATION": dict(**SCOPE, id="N"),
}


@pytest.fixture(scope="module")
def gw():
    try:
        return BigQueryGateway(get_settings())
    except Exception as e:   # no ADC, no SESSION_SIGNING_KEY...
        pytest.skip(f"BigQuery not configured: {e}")


def dry_run(gw, sql, params):
    config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params)
    gw.client.query(sql, job_config=config)   # raises on any compile or permission error


def test_every_statement_is_covered():
    names = {n for n, v in vars(queries).items() if n.isupper() and not n.startswith("_") and isinstance(v, str) and "SELECT" in v}
    assert names - {"FIND_TRANSACTIONS"} == set(STATEMENTS)   # FIND_TRANSACTIONS is built, see below


@pytest.mark.parametrize("name", sorted(STATEMENTS))
def test_statement_compiles(gw, name):
    dry_run(gw, getattr(queries, name).format(**_tables(gw)), sandbox.params(**STATEMENTS[name]))


def test_find_transactions_with_every_filter_compiles(gw):
    slots = TransactionSlots(amount="10", merchant="x", currency="USD")
    sql, params = build_find_query(slots=slots, customer_id="CLI-DRY", reference_date=NOW.date(), limit=3,
                                   window_days=90, tolerance_pct=1.0, transactions=gw.table("transactions"),
                                   products=gw.table("products"))
    dry_run(gw, sql, params)
