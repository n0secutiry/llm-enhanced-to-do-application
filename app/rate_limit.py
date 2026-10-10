"""A deliberately simple in-memory rate limiter for LLM-backed endpoints.

One process, one dictionary, a sliding window per client IP. That is enough to
stop a single client from hammering a local model. It is NOT shared between
workers or containers — a real deployment needs Redis for that.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import settings


class RateLimiter:
    def __init__(self, requests: int, window_s: int):
        self.requests = requests
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]

        while hits and now - hits[0] > self.window_s:
            hits.popleft()

        if len(hits) >= self.requests:
            retry_after = int(self.window_s - (now - hits[0])) + 1

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many LLM requests, slow down",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)


llm_rate_limiter = RateLimiter(
    requests=settings.LLM_RATE_LIMIT_REQUESTS,
    window_s=settings.LLM_RATE_LIMIT_WINDOW_S,
)


async def limit_llm_calls(request: Request) -> None:
    """FastAPI dependency: put it on every endpoint that calls the model."""
    client_ip = request.client.host if request.client else "unknown"

    llm_rate_limiter.check(client_ip)
