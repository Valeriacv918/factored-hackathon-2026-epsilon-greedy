"""Sandbox tools (block_card, file_dispute, read_*, dispute_context) with a fake gateway."""
import datetime as dt
import hashlib

import pytest
from google.cloud import bigquery
from mcp.server.mcpserver.exceptions import ToolError

from bank_mcp.config.settings import get_settings
from bank_mcp.services import sandbox, session
from bank_mcp.tools import server

KEY = "test-signing-key-" + "x" * 32
CLOCK = dt.datetime(2026, 6, 17, 12, tzinfo=dt.timezone.utc)
SCENARIO = {"scenario_clock": CLOCK, "products_run_id": "run-p", "transactions_run_id": "run-t",
            "products_ok": True, "transactions_ok": True}


class FakeGateway:
    """Answers by tool name: a list of rows, or a callable(params) -> rows."""

    def __init__(self, answers):
        self.answers, self.calls = {"scenario_state": [SCENARIO], **answers}, []

    def table(self, name):
        return f"`p.cur.{name}`"

    def sandbox_table(self, name):
        return f"`p.sbx.{name}`"

    def query(self, sql, params, *, tool):
        values = {p.name: p.values if isinstance(p, bigquery.ArrayQueryParameter) else p.value for p in params}
        self.calls.append((tool, sql, values))
        answer = self.answers.get(tool, [])
        return answer(values) if callable(answer) else answer

    def sent(self, tool):
        return [(sql, values) for name, sql, values in self.calls if name == tool]


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("SESSION_SIGNING_KEY", KEY)
    monkeypatch.setenv("SANDBOX_SCENARIO_ID", "demo-1")
    get_settings.cache_clear()
    monkeypatch.setattr(server, "_scenario_state", None)
    yield
    get_settings.cache_clear()


def use(monkeypatch, **answers):
    gw = FakeGateway(answers)
    monkeypatch.setattr(server, "_gw", lambda: gw)
    return gw


def token(customer="CLI-1"):
    return session.issue(customer, KEY.encode(), dt.timedelta(minutes=5))


def receipt(id_, digest, same_key=True):
    return [{"id": id_, "request_hash": digest, "same_key": same_key}]


BLOCK_HASH = sandbox.request_hash("block_card", card_id="PRD-1")


def test_request_hash_is_sha256_of_sorted_compact_json():
    expected = hashlib.sha256(b'{"action":"block_card","card_id":"PRD-1"}').hexdigest()
    assert BLOCK_HASH == expected


def test_sandbox_tools_refuse_without_a_scenario(monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO_ID", "")
    get_settings.cache_clear()
    gw = use(monkeypatch)
    for call in (lambda: server.block_card(token(), "PRD-1", "k1"),
                 lambda: server.read_block(token(), "BLK-1"),
                 lambda: server.file_dispute(token(), "TRX-1", "k1"),
                 lambda: server.read_dispute(token(), "CASE-1"),
                 lambda: server.dispute_context(token(), "TRX-1")):
        with pytest.raises(ToolError, match=server.SCENARIO_MISSING):
            call()
    assert gw.calls == []


def test_block_card_writes_for_the_token_customer_and_returns_the_receipt(monkeypatch):
    gw = use(monkeypatch, block_card=lambda p: receipt("BLK-9", BLOCK_HASH) if "products_run_id" in p else [])
    result = server.block_card(token("CLI-1"), "PRD-1", "conv-1:block_card:PRD-1")
    assert result.id == "BLK-9"
    (insert_sql, insert), (find_sql, find) = gw.sent("block_card")
    assert "INSERT INTO `p.sbx.card_blocks`" in insert_sql and "`p.cur.products`" in insert_sql
    assert insert["customer_id"] == "CLI-1" and insert["scenario_id"] == "demo-1"
    assert insert["request_hash"] == BLOCK_HASH and insert["block_id"].startswith("BLK-")
    assert find["products_run_id"] == "run-p" and find["idempotency_key"] == "conv-1:block_card:PRD-1"


def test_reusing_a_key_with_other_arguments_is_a_conflict(monkeypatch):
    use(monkeypatch, block_card=lambda p: receipt("BLK-9", "0" * 64) if "products_run_id" in p else [])
    with pytest.raises(ToolError, match="Idempotency key reused"):
        server.block_card(token(), "PRD-1", "k1")


def test_already_blocked_card_returns_the_earlier_block(monkeypatch):
    use(monkeypatch, block_card=lambda p: receipt("BLK-OLD", "f" * 64, same_key=False) if "products_run_id" in p else [])
    assert server.block_card(token(), "PRD-1", "k2").id == "BLK-OLD"


def test_ineligible_or_foreign_card_gets_one_generic_error(monkeypatch):
    use(monkeypatch)   # nothing inserted, nothing found
    with pytest.raises(ToolError, match="^Card cannot be blocked.$"):
        server.block_card(token(), "PRD-OF-SOMEONE-ELSE", "k1")


def test_every_write_rechecks_the_scenario_and_refuses_changed_curated(monkeypatch):
    gw = use(monkeypatch, block_card=lambda p: receipt("BLK-9", BLOCK_HASH) if "products_run_id" in p else [])
    server.block_card(token(), "PRD-1", "k1")
    server.block_card(token(), "PRD-1", "k1")
    assert len(gw.sent("scenario_state")) == 2
    gw.answers["scenario_state"] = [{**SCENARIO, "transactions_ok": False}]
    with pytest.raises(ToolError, match="Curated data changed"):
        server.block_card(token(), "PRD-1", "k1")
    assert len(gw.sent("block_card")) == 4   # the refused call wrote nothing


def test_unknown_scenario_is_refused(monkeypatch):
    use(monkeypatch, scenario_state=[])
    with pytest.raises(ToolError, match="Sandbox scenario not found"):
        server.file_dispute(token(), "TRX-1", "k1")


def test_reads_verify_exactly_one_row(monkeypatch):
    row = {"id": "BLK-9", "card_id": "PRD-1", "customer_id": "CLI-1", "status": "Blocked", "verified": True}
    gw = use(monkeypatch, read_block=[row])
    assert server.read_block(token(), "BLK-9").model_dump() == row
    assert gw.sent("read_block")[0][1]["customer_id"] == "CLI-1"
    gw.answers["read_block"] = []
    with pytest.raises(ToolError, match=server.NOT_VERIFIED):
        server.read_block(token(), "BLK-9")


def test_file_dispute_and_read_dispute(monkeypatch):
    digest = sandbox.request_hash("file_dispute", transaction_id="TRX-1")
    row = {"id": "CASE-1", "customer_id": "CLI-1", "transaction_id": "TRX-1", "status": "OPEN", "verified": True}
    gw = use(monkeypatch, file_dispute=lambda p: receipt("CASE-1", digest) if "transactions_run_id" in p else [],
             read_dispute=[row])
    assert server.file_dispute(token(), "TRX-1", "k1").id == "CASE-1"
    insert_sql, insert = gw.sent("file_dispute")[0]
    assert "INSERT INTO `p.sbx.disputes`" in insert_sql and insert["case_id"].startswith("CASE-")
    assert server.read_dispute(token(), "CASE-1").transaction_id == "TRX-1"
    gw.answers["file_dispute"] = []
    with pytest.raises(ToolError, match="^Transaction cannot be disputed.$"):
        server.file_dispute(token(), "TRX-2", "k2")


def test_dispute_context_counts_dispute_complaints_before_the_scenario_clock(monkeypatch):
    gw = use(monkeypatch, dispute_context=[{"owned": 1, "existing_case_id": None, "recent_dispute_count": 2}])
    result = server.dispute_context(token(), "TRX-1")
    assert result.model_dump() == {"existing_case_id": None, "recent_dispute_count": 2}
    sql, params = gw.sent("dispute_context")[0]
    assert "`p.cur.complaints`" in sql and "`p.sbx.disputes`" in sql
    assert params["subcategories"] == ["Cargo no reconocido", "Cobro indebido"]
    assert params["history_end"] == CLOCK and params["history_start"] == CLOCK - dt.timedelta(days=90)


def test_dispute_context_for_someone_elses_transaction(monkeypatch):
    use(monkeypatch, dispute_context=[{"owned": 0, "existing_case_id": None, "recent_dispute_count": 0}])
    with pytest.raises(ToolError, match="Transaction not found"):
        server.dispute_context(token(), "TRX-OTHER")


def test_cards_show_effective_status_and_scenario_is_cached_for_reads(monkeypatch):
    gw = use(monkeypatch)
    server.list_cards(token())
    server.list_cards(token())
    with pytest.raises(ToolError, match="Card not found"):
        server.get_card(token(), "PRD-1")
    assert len(gw.sent("scenario_state")) == 1
    sql, params = gw.sent("get_card")[0]
    assert "`p.sbx.card_blocks`" in sql and params["products_run_id"] == "run-p" and params["card_id"] == "PRD-1"


def test_find_transactions_uses_the_scenario_clock(monkeypatch):
    gw = use(monkeypatch)
    server.find_transactions(token(), dt.date(2020, 1, 1), 30)
    params = gw.sent("find_transactions")[0][1]
    assert params["end_ts"] == dt.datetime(2026, 6, 18, tzinfo=dt.timezone.utc)
    assert params["start_ts"] == dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc)
