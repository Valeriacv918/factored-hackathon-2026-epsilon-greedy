"""McpIdentityChecker: parsing of the server's verify_identity answers."""
from datetime import date, datetime, timezone

import pytest

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.clients.identity import McpIdentityChecker


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
