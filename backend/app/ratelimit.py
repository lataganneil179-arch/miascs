"""Small in-memory failure throttle for login attempts.

State is per process. If you run several workers or instances, move this to
a shared store (e.g. Redis) so the limit applies across all of them.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, status


class LoginThrottle:
    def __init__(self, window_seconds: int) -> None:
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        bucket = self._failures[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if not bucket:
            self._failures.pop(key, None)
            return deque()
        return bucket

    def ensure_allowed(self, key: str, limit: int) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._prune(key, now)
            if len(bucket) >= limit:
                retry_after = int(self.window - (now - bucket[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed attempts. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(time.monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
