import base64
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from bank_agent.clients.identity import CustomerRecord, InMemoryIdentityChecker, Product
from bank_agent.clients.sessions import StaticSessions, ValidatorSessions, token_customer
from bank_agent.nodes.validator_agent.validator import IdentityValidator


def token(claims, signature="sig"):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{payload}.{signature}"


def test_static_sessions_read_customer_from_token():
    t = token({"sub": "CLI-1", "exp": 1})
    grant = StaticSessions.from_string(f"dev = {t}").resolve("dev")
    assert (grant.customer_id, grant.token) == ("CLI-1", t)
    assert StaticSessions.from_string("").resolve("dev") is None


@pytest.mark.parametrize("spec", ["dev=CLI-1", "dev", "=x", f"dev={token({'exp': 1})}", f"dev={token({'sub': ''})}"])
def test_static_sessions_reject_entries_that_are_not_tokens(spec):
    with pytest.raises(ValueError):
        StaticSessions.from_string(spec)


def test_token_never_shows_in_repr_or_errors():
    t = token({"sub": "CLI-1"}, signature="SECRET")
    assert "SECRET" not in repr(StaticSessions({"dev": t}).resolve("dev"))
    with pytest.raises(ValueError) as exc:
        token_customer("SECRET")
    assert "SECRET" not in str(exc.value)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def test_validator_sessions_follow_authentication_and_ttl():
    clock = Clock()
    # The customer types their document; the session keeps the internal customer_id.
    customers = {"1020304050": CustomerRecord("CLI-0001", date(1990, 4, 3), (Product("4111222233334444"),))}
    validator = IdentityValidator(InMemoryIdentityChecker(customers, clock=clock), clock=clock)
    sessions = ValidatorSessions(validator)
    sid = validator.new_session().session_id
    assert sessions.resolve(sid) is None and sessions.resolve("unknown") is None

    validator.verify(sid, "1.020.304.050", "03/04/1990", "4111 2222 3333 4444")
    grant = sessions.resolve(sid)
    assert (grant.customer_id, grant.token) == ("CLI-0001", "test-token:CLI-0001")

    clock.now += timedelta(minutes=16)
    assert sessions.resolve(sid) is None
    assert validator.get_session(sid).session_token is None
