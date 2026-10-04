"""Sandbox tools (block_card, file_dispute, create_handoff, notify_employee, read_*, dispute_context) with a fake gateway.

These check what Python decides and sends: the customer from the token, the scenario,
run ids, hashes, refusals. Eligibility, ownership and dedupe live in the SQL; the
opt-in test_sql_dry_run.py checks that against BigQuery.
"""
import datetime as dt
import hashlib
import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from bank_mcp.config.settings import get_settings
from bank_mcp.services import sandbox
from bank_mcp.tools import server

CLOCK = dt.datetime(2026, 6, 17, 12, tzinfo=dt.timezone.utc)
SCENARIO = {"scenario_clock": CLOCK, "products_run_id": "run-p", "transactions_run_id": "run-t",
            "products_ok": True, "transactions_ok": True}
BLOCK_HASH = sandbox.request_hash("block_card", card_id="PRD-1")
PACKET = {"reason": "card_replacement", "queue": "cards", "priority": "P3", "language": "es",
          "customer_quote": "perdí mi tarjeta", "transaction_ids": ["TRX-1"], "case_ids": ["CASE-1"],
          "blocked_cards": ["PRD-1", "PRD-1"], "suspended_accounts": [], "not_done": ["card_replacement"],
          "next_steps": ["human_review"], "policy_version": "demo-v4", "narrative": "Escalado a la cola cards.",
          "narrative_source": "template", "claim_issues": []}


@pytest.fixture(autouse=True)
def scenario(monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO_ID", "demo-1")
    get_settings.cache_clear()


@pytest.fixture
def use(gateway):
    """A gateway where scenario demo-1 exists, unless the test overrides scenario_state."""
    return lambda **answers: gateway(**{"scenario_state": [SCENARIO], **answers})


def receipt(id_, digest, same_key=True):
    return [{"id": id_, "request_hash": digest, "same_key": same_key}]


def test_request_hash_is_sha256_of_sorted_compact_json():
    expected = hashlib.sha256(b'{"action":"block_card","card_id":"PRD-1"}').hexdigest()
    assert BLOCK_HASH == expected


def test_sandbox_tools_refuse_without_a_scenario(monkeypatch, use, token):
    monkeypatch.setenv("SANDBOX_SCENARIO_ID", "")
    get_settings.cache_clear()
    gw = use()
    for call in (lambda: server.block_card(token(), "PRD-1", "k1"),
                 lambda: server.read_block(token(), "BLK-1"),
                 lambda: server.file_dispute(token(), "TRX-1", "k1"),
                 lambda: server.read_dispute(token(), "CASE-1"),
                 lambda: server.dispute_context(token(), "TRX-1"),
                 lambda: server.create_handoff(token(), server.HandoffPacket(**PACKET), "k1"),
                 lambda: server.read_handoff(token(), "TKT-1"),
                 lambda: server.notify_employee(token(), "TKT-1", "k1"),
                 lambda: server.read_notification(token(), "NTF-1")):
        with pytest.raises(ToolError, match=server.SCENARIO_MISSING):
            call()
    assert gw.calls == []


def test_block_card_writes_for_the_token_customer_and_returns_the_receipt(use, token):
    gw = use(block_card=lambda p: receipt("BLK-9", BLOCK_HASH) if "products_run_id" in p else [])
    result = server.block_card(token("CLI-1"), "PRD-1", "conv-1:block_card:PRD-1")
    assert result.id == "BLK-9"
    (insert_sql, insert), (find_sql, find) = gw.sent("block_card")
    assert "INSERT INTO `p.sbx.card_blocks`" in insert_sql and "`p.cur.products`" in insert_sql
    assert insert["customer_id"] == "CLI-1" and insert["scenario_id"] == "demo-1"
    assert insert["request_hash"] == BLOCK_HASH and insert["block_id"].startswith("BLK-")
    assert find["products_run_id"] == "run-p" and find["idempotency_key"] == "conv-1:block_card:PRD-1"


def test_reusing_a_key_with_other_arguments_is_a_conflict(use, token):
    use(block_card=lambda p: receipt("BLK-9", "0" * 64) if "products_run_id" in p else [])
    with pytest.raises(ToolError, match="Idempotency key reused"):
        server.block_card(token(), "PRD-1", "k1")


def test_an_earlier_block_under_another_key_is_not_a_conflict(use, token):
    # Its hash differs, but same_key=False means "the earlier event on this card", not a reused key.
    use(block_card=lambda p: receipt("BLK-OLD", "f" * 64, same_key=False) if "products_run_id" in p else [])
    assert server.block_card(token(), "PRD-1", "k2").id == "BLK-OLD"


def test_ineligible_or_foreign_card_gets_one_generic_error(use, token):
    use()   # nothing inserted, nothing found
    with pytest.raises(ToolError, match="^Card cannot be blocked.$"):
        server.block_card(token(), "PRD-OF-SOMEONE-ELSE", "k1")


def test_every_write_rechecks_the_scenario_and_refuses_changed_curated(use, token):
    gw = use(block_card=lambda p: receipt("BLK-9", BLOCK_HASH) if "products_run_id" in p else [])
    server.block_card(token(), "PRD-1", "k1")
    server.block_card(token(), "PRD-1", "k1")
    assert len(gw.sent("scenario_state")) == 2
    gw.answers["scenario_state"] = [{**SCENARIO, "transactions_ok": False}]
    with pytest.raises(ToolError, match="Curated data changed"):
        server.block_card(token(), "PRD-1", "k1")
    assert len(gw.sent("block_card")) == 4   # the refused call wrote nothing


def test_unknown_scenario_is_refused(use, token):
    use(scenario_state=[])
    with pytest.raises(ToolError, match="Sandbox scenario not found"):
        server.file_dispute(token(), "TRX-1", "k1")


READS = {
    "read_block": {"id": "R-1", "card_id": "PRD-1", "customer_id": "CLI-1", "status": "Blocked", "verified": True},
    "read_dispute": {"id": "R-1", "customer_id": "CLI-1", "transaction_id": "TRX-1", "status": "OPEN",
                     "verified": True},
    "read_handoff": {"id": "R-1", "customer_id": "CLI-1", "verified": True},
    "read_notification": {"id": "R-1", "ticket_id": "TKT-1", "customer_id": "CLI-1", "status": "SIMULATED",
                          "verified": True},
}


@pytest.mark.parametrize("tool", sorted(READS))
def test_reads_verify_exactly_one_row_of_the_token_customer(use, token, tool):
    read = getattr(server, tool)
    row = READS[tool]
    gw = use(**{tool: [row]})
    assert read(token("CLI-1"), "R-1").model_dump() == row
    (_, params), = gw.sent(tool)
    assert params["customer_id"] == "CLI-1" and params["scenario_id"] == "demo-1" and params["id"] == "R-1"
    for rows in ([], [row, row]):
        gw.answers[tool] = rows
        with pytest.raises(ToolError, match=server.NOT_VERIFIED):
            read(token(), "R-1")


def test_file_dispute(use, token):
    digest = sandbox.request_hash("file_dispute", transaction_id="TRX-1")
    gw = use(file_dispute=lambda p: receipt("CASE-1", digest) if "transactions_run_id" in p else [])
    assert server.file_dispute(token(), "TRX-1", "k1").id == "CASE-1"
    insert_sql, insert = gw.sent("file_dispute")[0]
    assert "INSERT INTO `p.sbx.disputes`" in insert_sql and insert["case_id"].startswith("CASE-")
    gw.answers["file_dispute"] = []
    with pytest.raises(ToolError, match="^Transaction cannot be disputed.$"):
        server.file_dispute(token(), "TRX-2", "k2")


def test_dispute_context_counts_dispute_complaints_before_the_scenario_clock(use, token):
    gw = use(dispute_context=[{"owned": 1, "existing_case_id": None, "recent_dispute_count": 2}])
    result = server.dispute_context(token(), "TRX-1")
    assert result.model_dump() == {"existing_case_id": None, "recent_dispute_count": 2}
    sql, params = gw.sent("dispute_context")[0]
    assert "`p.cur.complaints`" in sql and "`p.sbx.disputes`" in sql
    assert params["subcategories"] == ["Cargo no reconocido", "Cobro indebido"]
    assert params["history_end"] == CLOCK and params["history_start"] == CLOCK - dt.timedelta(days=90)


def test_dispute_context_for_someone_elses_transaction(use, token):
    use(dispute_context=[{"owned": 0, "existing_case_id": None, "recent_dispute_count": 0}])
    with pytest.raises(ToolError, match="Transaction not found"):
        server.dispute_context(token(), "TRX-OTHER")


def test_cards_show_effective_status_and_scenario_is_cached_for_reads(use, token):
    gw = use()
    server.list_cards(token())
    server.list_cards(token())
    with pytest.raises(ToolError, match="Card not found"):
        server.get_card(token(), "PRD-1")
    assert len(gw.sent("scenario_state")) == 1
    sql, params = gw.sent("get_card")[0]
    assert "`p.sbx.card_blocks`" in sql and params["products_run_id"] == "run-p" and params["card_id"] == "PRD-1"


def test_find_transactions_uses_the_scenario_clock(use, token):
    gw = use()
    server.find_transactions(token(), dt.date(2020, 1, 1), 30)
    params = gw.sent("find_transactions")[0][1]
    assert params["end_ts"] == dt.datetime(2026, 6, 18, tzinfo=dt.timezone.utc)
    assert params["start_ts"] == dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc)


@pytest.fixture
def handoff(use):
    """create_handoff runs three statements under one tool name: refs, insert, receipt lookup."""
    def install(refs=None, digest=None):
        packet = server.HandoffPacket(**PACKET).model_dump(mode="json")
        digest = digest or sandbox.request_hash("create_handoff", packet=packet)
        counts = refs or {"transactions": 1, "cases": 1, "cards": 1}

        def answer(p):
            if "transaction_ids" in p:
                return [counts]
            return [] if "packet" in p else receipt("TKT-1", digest)
        return use(create_handoff=answer)
    return install


def test_create_handoff_checks_ownership_then_writes_the_packet(handoff, token):
    gw = handoff()
    result = server.create_handoff(token("CLI-1"), server.HandoffPacket(**PACKET), "conv-1:create_handoff:handoff")
    assert result.id == "TKT-1"
    (refs_sql, refs), (insert_sql, insert), _ = gw.sent("create_handoff")
    assert refs["customer_id"] == "CLI-1" and refs["card_ids"] == ["PRD-1"]   # duplicates counted once
    assert refs["transactions_run_id"] == "run-t" and refs["products_run_id"] == "run-p"
    assert "INSERT INTO `p.sbx.handoffs`" in insert_sql and "`p.cur.customers`" in insert_sql
    assert insert["ticket_id"].startswith("TKT-") and insert["customer_id"] == "CLI-1"
    assert json.loads(insert["packet"])["customer_quote"] == "perdí mi tarjeta"


def test_handoff_citing_someone_elses_item_is_refused_before_writing(handoff, token):
    gw = handoff(refs={"transactions": 0, "cases": 1, "cards": 1})
    with pytest.raises(ToolError, match="not the customer's"):
        server.create_handoff(token(), server.HandoffPacket(**PACKET), "k1")
    assert len(gw.sent("create_handoff")) == 1


def test_handoff_key_reused_with_another_packet_is_a_conflict(handoff, token):
    handoff(digest="0" * 64)
    with pytest.raises(ToolError, match="Idempotency key reused"):
        server.create_handoff(token(), server.HandoffPacket(**PACKET), "k1")


@pytest.mark.parametrize("change", [{"session_token": "x"}, {"customer_quote": "x" * 1001},
                                    {"suspended_accounts": ["ACC-1"]}, {"priority": "P0"},
                                    {"transaction_ids": ["TRX 1"]}, {"narrative": ""}])
def test_handoff_packet_schema_is_strict(change):
    with pytest.raises(ValidationError):
        server.HandoffPacket(**{**PACKET, **change})


def test_notify_employee_once_per_ticket(use, token):
    digest = sandbox.request_hash("notify_employee", ticket_id="TKT-1")
    gw = use(notify_employee=lambda p: [] if "delivery_id" in p else receipt("NTF-1", "f" * 64, same_key=False))
    assert server.notify_employee(token("CLI-1"), "TKT-1", "k2").id == "NTF-1"   # earlier notification, other key
    insert_sql, insert = gw.sent("notify_employee")[0]
    assert "INSERT INTO `p.sbx.notifications`" in insert_sql and "`p.sbx.handoffs`" in insert_sql
    assert insert["request_hash"] == digest and insert["customer_id"] == "CLI-1"
    gw.answers["notify_employee"] = []
    with pytest.raises(ToolError, match="^Ticket not found.$"):
        server.notify_employee(token(), "TKT-OTHER", "k3")
