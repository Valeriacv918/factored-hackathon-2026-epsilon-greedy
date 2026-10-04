"""McpIdentityChecker: what it sends to verify_identity, how it parses the answers, and
how the validated session supplies the token to McpServices."""
from datetime import date, datetime, timedelta, timezone

import pytest

from bank_agent.clients.contracts import ServiceFailure, SessionExpired
from bank_agent.clients.identity import McpIdentityChecker
from bank_agent.clients.mcp_services import McpServices
from bank_agent.clients.sessions import StaticSessions
from bank_agent.nodes.validator_agent.validator import IdentityValidator, Status


class FakeClient:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return self.answer


def check(answer):
    client = FakeClient(answer)
    return McpIdentityChecker(client).verify("1020304050", date(1990, 4, 3), "4111222233334444"), client


def test_sends_iso_date_and_only_the_three_values():
    _, client = check({"status": "failed", "attempts_left": 2})
    assert client.calls == [("verify_identity", {"document_number": "1020304050", "date_of_birth": "1990-04-03",
                                                 "product_number": "4111222233334444"})]


def test_parses_server_limits():
    verified, _ = check({"status": "verified", "customer_id": "CLI-1", "session_token": "t", "product_numbers": ["1", "2"],
                         "expires_at": "2026-10-01T12:15:00+00:00"})
    assert (verified.customer_id, verified.product_numbers, verified.session_token) == ("CLI-1", ("1", "2"), "t")
    assert verified.expires_at == datetime(2026, 10, 1, 12, 15, tzinfo=timezone.utc)
    assert check({"status": "failed", "attempts_left": 2})[0].attempts_left == 2
    locked, _ = check({"status": "locked", "locked_until": "2026-10-01T12:15:00+00:00"})
    assert locked.locked_until == datetime(2026, 10, 1, 12, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize("answer", [
    {"status": "verified", "customer_id": "CLI-1", "product_numbers": [],
     "expires_at": "2026-10-01T12:15:00+00:00"},                                                  # no token
    {"status": "verified", "session_token": "t", "expires_at": "2026-10-01T12:15:00+00:00"},    # no customer_id
    {"status": "verified", "session_token": "t"},                                               # no expiry
    {"status": "verified", "session_token": "t", "expires_at": "2026-10-01T12:15:00"},          # naive time
    {"status": "failed"},
    {"status": "locked", "locked_until": "soon"},
    {"status": "maybe"},
])
def test_malformed_answers_are_service_failures(answer):
    with pytest.raises(ServiceFailure):
        check(answer)


def verified_answer():
    return {"status": "verified", "customer_id": "CLI-ONE", "product_numbers": ["12345678"],
            "session_token": "signed-token", "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}


def test_validator_normalizes_before_asking_the_server():
    client = FakeClient(verified_answer())
    v = IdentityValidator(McpIdentityChecker(client))
    sid = v.new_session().session_id
    assert v.verify(sid, "1.020.304.050", "1990-04-03", "1234 5678").status == Status.VERIFIED
    assert client.calls == [("verify_identity", {"document_number": "1020304050", "date_of_birth": "1990-04-03",
                                                 "product_number": "12345678"})]
    session = v.get_session(sid)
    assert (session.customer_id, session.session_token) == ("CLI-ONE", "signed-token")
    assert v.can_access_product(sid, "12345678")


def test_validated_session_supplies_the_token_until_it_expires():
    client = FakeClient(verified_answer())
    services = McpServices(client, StaticSessions({}), None)
    v = services._identity_validator = IdentityValidator(McpIdentityChecker(client))
    sid = v.new_session().session_id
    v.verify(sid, "1020304050", "1990-04-03", "12345678")
    client.answer = {"cards": []}
    services.tool("list_cards", session_ref=sid, customer_id="CLI-ONE", arguments={})
    assert client.calls[-1] == ("list_cards", {"session_token": "signed-token"})
    v.get_session(sid).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(SessionExpired):
        services.tool("list_cards", session_ref=sid, customer_id="CLI-ONE", arguments={})
    assert len(client.calls) == 2   # the expired session never reached the server
