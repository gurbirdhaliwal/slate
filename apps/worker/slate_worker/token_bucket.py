"""Thread-safe token bucket for the Anthropic call budget (ANTHROPIC_MAX_CALLS_PER_10S)."""

from __future__ import annotations

import threading
import time


class TokenBucket:
    def __init__(self, max_calls: int, per_seconds: float = 10.0) -> None:
        self._capacity = float(max_calls)
        self._tokens = float(max_calls)
        self._refill_rate = max_calls / per_seconds  # tokens per second
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a token is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._refill_rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._refill_rate
            time.sleep(wait)
