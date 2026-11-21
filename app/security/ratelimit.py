"""Tiny in-memory sliding-window rate limiter (per client IP)."""
import time
from collections import defaultdict, deque

_hits: dict[str, deque] = defaultdict(deque)


def allow(key: str, limit: int = 20, window: float = 60.0) -> bool:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True
