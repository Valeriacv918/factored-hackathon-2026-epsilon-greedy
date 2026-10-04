"""verify_identity with a fake gateway: parameters, signed session and lockout."""
import datetime as dt

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from bank_mcp.services import session
from bank_mcp.tools import server

BIRTH = dt.date(1990, 4, 3)
MATCH = [{"customer_id": "CLI-ONE", "product_numbers": ["87654321", "12345678"]}]


def test_verified_returns_signed_session_and_sorted_products(gateway, signing_key):
    gw = gateway(verify_identity=MATCH)
    r = server.verify_identity("1.020.304.050", BIRTH, "1234-5678")
    assert r.status == "verified" and r.customer_id == "CLI-ONE"
    assert session.verify(r.session_token, signing_key) == "CLI-ONE"
    assert r.product_numbers == ["12345678", "87654321"]
    assert dt.datetime.fromisoformat(r.expires_at).tzinfo is not None
    (_, params), = gw.sent("verify_identity")
    # Normalized like the SQL, and the caller can never pass a customer_id.
    assert params == {"document_number": "1020304050", "date_of_birth": BIRTH, "product_number": "12345678"}


def test_failures_count_down_then_lock_without_querying(gateway):
    gw = gateway(verify_identity=[])
    results = [server.verify_identity("1020304050", BIRTH, "12345678") for _ in range(3)]
    assert [(r.status, r.attempts_left) for r in results] == [("failed", 2), ("failed", 1), ("locked", None)]
    assert all(r.customer_id is None and r.session_token is None for r in results)
    gw.answers["verify_identity"] = MATCH   # even the right answer is refused while locked
    locked = server.verify_identity("1.020.304.050", BIRTH, "12345678")
    assert locked.status == "locked" and locked.locked_until == results[-1].locked_until
    assert len(gw.sent("verify_identity")) == 3


def test_success_resets_failed_attempts(gateway):
    gw = gateway(verify_identity=[])
    server.verify_identity("1020304050", BIRTH, "12345678")
    gw.answers["verify_identity"] = MATCH
    server.verify_identity("1020304050", BIRTH, "12345678")
    gw.answers["verify_identity"] = []
    assert server.verify_identity("1020304050", BIRTH, "12345678").attempts_left == 2


def test_two_customers_with_the_same_document_fail_closed(gateway):
    gateway(verify_identity=MATCH + [{"customer_id": "CLI-TWO", "product_numbers": ["12345678"]}])
    with pytest.raises(ToolError, match="inconsistent"):
        server.verify_identity("1020304050", BIRTH, "12345678")
