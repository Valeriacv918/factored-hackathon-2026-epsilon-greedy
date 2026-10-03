"""Process-wide token bucket shared by all tools."""
import threading
import time


class RateLimited(RuntimeError):
    pass


class TokenBucket:
    def __init__(self, per_minute: int) -> None:
        self.capacity = float(per_minute)
        self.tokens = float(per_minute)
        self.rate = per_minute / 60.0
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def take(self) -> None:
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                raise RateLimited(f"Rate limit exceeded; retry in {wait:.0f}s.")
            self.tokens -= 1
