"""verify_identity and session-token enforcement on the data tools, with a fake gateway."""
import asyncio
import datetime as dt

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from bank_mcp.config.settings import get_settings
from bank_mcp.services import session
from bank_mcp.tools import server

KEY = "test-signing-key-" + "x" * 32
DOB = dt.date(1990, 4, 3)


class FakeGateway:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def table(self, name):
        return f"`p.d.{name}`"

    def query(self, sql, params, *, tool):
        self.calls.append((tool, sql, {p.name: getattr(p, "value", None) or getattr(p, "values", None) for p in params}))
        return self.rows(self.calls[-1][2]) if callable(self.rows) else self.rows


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("SESSION_SIGNING_KEY", KEY)
    monkeypatch.setenv("IDENTITY_MAX_ATTEMPTS", "3")
    get_settings.cache_clear()
    monkeypatch.setattr(server, "_throttle", None)
    yield
    get_settings.cache_clear()


def use(monkeypatch, rows):
    gw = FakeGateway(rows)
    monkeypatch.setattr(server, "_gw", lambda: gw)
    return gw


def known_customer(params):
    """Document 1020304050 is CLI-1, born 1990-04-03, owns product 4111222233334444."""
    ok = (params["document_number"] == "1020304050" and params["date_of_birth"] == DOB
          and params["product_number"] == "4111222233334444")
    return [{"customer_id": "CLI-1", "product_numbers": ["4111222233334444", "00987654321"]}] if ok else []


def test_verified_returns_token_for_that_customer_and_no_personal_data(monkeypatch):
    gw = use(monkeypatch, known_customer)
    result = server.verify_identity("1.020.304.050", DOB, "4111 2222-3333 4444")
    assert result.status == "verified" and result.customer_id == "CLI-1"
    assert result.product_numbers == ["00987654321", "4111222233334444"]
    assert session.verify(result.session_token, KEY.encode()) == "CLI-1"
    # expires_at is exactly the token's expiry (15 minutes, whole seconds).
    expires = dt.datetime.fromisoformat(result.expires_at)
    assert dt.timedelta(minutes=14) < expires - dt.datetime.now(dt.timezone.utc) <= dt.timedelta(minutes=15)
    assert session.verify(result.session_token, KEY.encode(), clock=lambda: expires - dt.timedelta(seconds=1))
    with pytest.raises(session.InvalidSession):
        session.verify(result.session_token, KEY.encode(), clock=lambda: expires)
    assert "1990" not in result.model_dump_json()
    # Document and product number are normalized before they reach SQL; the DOB is a DATE parameter.
    _, sql, params = gw.calls[0]
    assert params["document_number"] == "1020304050" and params["product_number"] == "4111222233334444"
    assert "document_number" in sql and "date_of_birth = @date_of_birth" in sql
    assert "SELECT c.customer_id, ARRAY_AGG" in sql


@pytest.mark.parametrize("args", [("1020304050", dt.date(1990, 4, 4), "4111222233334444"),
                                  ("1020304050", DOB, "9999888877776666"),
                                  ("9999999999", DOB, "4111222233334444"),
                                  ("CLI-1", DOB, "4111222233334444")])   # the internal ID is not a document
def test_wrong_answer_and_unknown_customer_look_the_same(monkeypatch, args):
    use(monkeypatch, known_customer)
    result = server.verify_identity(*args)
    # Unknown customers count attempts exactly like real ones: no enumeration oracle.
    assert result.model_dump() == {"status": "failed", "customer_id": None, "session_token": None, "product_numbers": [],
                                   "attempts_left": 2, "locked_until": None, "expires_at": None}


def test_locks_after_max_attempts_without_querying_again(monkeypatch):
    gw = use(monkeypatch, known_customer)
    # "1.020.304.050" and "1020304050" are the same document: they share the counter.
    results = [server.verify_identity(doc, DOB, "0000") for doc in ("1020304050", "1.020.304.050", "1020-304-050")]
    assert [(r.status, r.attempts_left) for r in results] == [("failed", 2), ("failed", 1), ("locked", None)]
    until = dt.datetime.fromisoformat(results[-1].locked_until)
    assert dt.timedelta(minutes=14) < until - dt.datetime.now(dt.timezone.utc) <= dt.timedelta(minutes=15)
    # Even the right answer is refused while locked, and BigQuery is not queried.
    locked = server.verify_identity("1020304050", DOB, "4111222233334444")
    assert (locked.status, locked.locked_until, locked.session_token) == ("locked", results[-1].locked_until, None)
    assert len(gw.calls) == 3


def test_two_customers_with_the_same_document_never_authenticate(monkeypatch):
    use(monkeypatch, [{"customer_id": "CLI-1", "product_numbers": ["1234"]},
                      {"customer_id": "CLI-2", "product_numbers": ["1234"]}])
    with pytest.raises(ToolError):
        server.verify_identity("1020304050", DOB, "1234")


def test_data_tools_take_customer_from_token(monkeypatch):
    gw = use(monkeypatch, [])
    token = session.issue("CLI-1", KEY.encode(), dt.timedelta(minutes=5))
    server.list_cards(token)
    assert gw.calls[-1][2]["customer_id"] == "CLI-1"


@pytest.mark.parametrize("token", ["", "CLI-1", "garbage.token"])
def test_data_tools_reject_bad_tokens_before_querying(monkeypatch, token):
    gw = use(monkeypatch, [])
    for call in (lambda: server.list_cards(token), lambda: server.get_card(token, "PRD-1"),
                 lambda: server.find_transactions(token, dt.date(2026, 6, 18), 90)):
        with pytest.raises(ToolError, match=server.SESSION_INVALID):
            call()
    assert gw.calls == []


def test_tokens_signed_with_another_key_or_expired_are_rejected(monkeypatch):
    use(monkeypatch, [])
    forged = session.issue("CLI-1", b"attacker-key-" + b"x" * 32, dt.timedelta(minutes=5))
    expired = session.issue("CLI-1", KEY.encode(), dt.timedelta(minutes=5),
                            clock=lambda: dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1))
    for token in (forged, expired):
        with pytest.raises(ToolError, match=server.SESSION_INVALID):
            server.list_cards(token)


def test_tool_schemas_no_longer_accept_customer_id():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in ("find_transactions", "list_cards", "get_card"):
        assert "customer_id" not in tools[name].input_schema["properties"]
        assert "session_token" in tools[name].input_schema["required"]
