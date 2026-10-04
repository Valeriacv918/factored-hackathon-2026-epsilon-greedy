import datetime as dt

import pytest

from bank_mcp.services import session
from bank_mcp.services.session import InvalidSession, LoginThrottle

KEY = b"k" * 32
T0 = dt.datetime(2026, 6, 18, 12, tzinfo=dt.timezone.utc)
TTL = dt.timedelta(minutes=15)


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


def token(customer_id="CLI-1", key=KEY, clock=None):
    return session.issue(customer_id, key, TTL, clock or Clock())


def test_round_trip_returns_customer():
    assert session.verify(token(), KEY, Clock()) == "CLI-1"


def test_expired_token_is_rejected():
    assert session.verify(token(), KEY, Clock(T0 + TTL - dt.timedelta(seconds=1))) == "CLI-1"
    with pytest.raises(InvalidSession):
        session.verify(token(), KEY, Clock(T0 + TTL))


def test_wrong_key_is_rejected():
    with pytest.raises(InvalidSession):
        session.verify(token(), b"x" * 32, Clock())


def test_tampered_payload_is_rejected():
    # Swap in another customer's payload but keep the original signature.
    _, signature = token("CLI-1").split(".")
    other_payload, _ = token("CLI-2").split(".")
    with pytest.raises(InvalidSession):
        session.verify(f"{other_payload}.{signature}", KEY, Clock())


def test_tampered_signature_is_rejected():
    payload, signature = token().split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(InvalidSession):
        session.verify(f"{payload}.{flipped}", KEY, Clock())


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "!!!.???", "CLI-1", ".", "e30.e30"])
def test_garbage_is_rejected(garbage):
    with pytest.raises(InvalidSession):
        session.verify(garbage, KEY, Clock())


def test_signed_payload_with_bad_claims_is_rejected():
    # A correctly signed payload is still rejected if its claims are malformed.
    for payload in (session._b64(b"[]"), session._b64(b'{"sub": "", "exp": 9999999999}'),
                    session._b64(b'{"sub": "CLI-1", "exp": "never"}')):
        with pytest.raises(InvalidSession):
            session.verify(f"{payload}.{session._sign(KEY, payload)}", KEY, Clock())


def test_throttle_locks_after_max_attempts_then_expires():
    clock = Clock()
    t = LoginThrottle(3, dt.timedelta(minutes=15), clock)
    assert [t.failed("CLI-1") for _ in range(3)] == [2, 1, 0]
    assert t.locked_until("CLI-1") == T0 + dt.timedelta(minutes=15)
    assert t.is_locked("CLI-1") and t.locked_until("CLI-2") is None
    clock.now = T0 + dt.timedelta(minutes=15)
    assert not t.is_locked("CLI-1") and t.locked_until("CLI-1") is None


def test_throttle_success_resets_failures():
    t = LoginThrottle(3, dt.timedelta(minutes=15), Clock())
    t.failed("CLI-1")
    t.failed("CLI-1")
    t.succeeded("CLI-1")
    assert t.failed("CLI-1") == 2


def test_throttle_keeps_only_hashes():
    t = LoginThrottle(3, dt.timedelta(minutes=15), Clock())
    t.failed("CLI-1")
    assert "CLI-1" not in repr(t._failures)
