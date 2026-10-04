"""Session tokens and login throttling: the server, not the caller, decides who the customer is.

A token is `base64url(json{sub, iat, exp}) . base64url(hmac_sha256(payload))`, signed with
SESSION_SIGNING_KEY. It is stateless, so it works across Cloud Run instances. Tools take the
token and read customer_id from it; they never accept customer_id as an argument.

LoginThrottle limits verify_identity attempts per customer. It lives in memory, so each
server instance counts on its own: enough for the demo, not for many instances.
"""
import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
import threading
from typing import Callable

Clock = Callable[[], dt.datetime]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class InvalidSession(Exception):
    """Bad signature, expired, or malformed. The caller gets one generic message."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(key: bytes, payload: str) -> str:
    return _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())


def issue(customer_id: str, key: bytes, ttl: dt.timedelta, clock: Clock = utc_now) -> str:
    now = int(clock().timestamp())
    payload = _b64(json.dumps({"sub": customer_id, "iat": now, "exp": now + int(ttl.total_seconds())},
                              separators=(",", ":")).encode())
    return f"{payload}.{_sign(key, payload)}"


def verify(token: str, key: bytes, clock: Clock = utc_now) -> str:
    """Return the token's customer_id, or raise InvalidSession."""
    try:
        payload, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(key, payload)):
            raise InvalidSession()
        claims = json.loads(_unb64(payload))
        customer_id, exp = claims["sub"], claims["exp"]
    except (ValueError, KeyError, TypeError, binascii.Error, AttributeError):
        raise InvalidSession() from None
    if not isinstance(customer_id, str) or not customer_id or not isinstance(exp, int):
        raise InvalidSession()
    if clock().timestamp() >= exp:
        raise InvalidSession()
    return customer_id


class LoginThrottle:
    """Lock a customer after `max_attempts` failed identity checks, for `lockout`."""

    def __init__(self, max_attempts: int, lockout: dt.timedelta, clock: Clock = utc_now):
        self.max_attempts, self.lockout, self.clock = max_attempts, lockout, clock
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, dt.datetime] = {}

    @staticmethod
    def _key(customer_id: str) -> str:
        # Keep no customer IDs in memory, only their hashes.
        return hashlib.sha256(customer_id.encode()).hexdigest()

    def locked_until(self, customer_id: str) -> dt.datetime | None:
        """When the lockout ends, or None if the customer is not locked."""
        with self._lock:
            until = self._locked_until.get(self._key(customer_id))
            return until if until is not None and self.clock() < until else None

    def is_locked(self, customer_id: str) -> bool:
        return self.locked_until(customer_id) is not None

    def failed(self, customer_id: str) -> int:
        """Record a failure; return the attempts left (0 means the customer is now locked).

        Any customer_id string counts, known or not, so the answer reveals nothing
        about whether the customer exists."""
        key = self._key(customer_id)
        with self._lock:
            self._failures[key] = self._failures.get(key, 0) + 1
            left = self.max_attempts - self._failures[key]
            if left > 0:
                return left
            self._failures.pop(key)
            self._locked_until[key] = self.clock() + self.lockout
            return 0

    def succeeded(self, customer_id: str) -> None:
        key = self._key(customer_id)
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)
