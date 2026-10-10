"""Rate limiter tests: pure logic, no HTTP server needed."""

import pytest
from fastapi import HTTPException

from app.rate_limit import RateLimiter


def test_requests_within_the_limit_pass():
    limiter = RateLimiter(requests=3, window_s=60)

    for _ in range(3):
        limiter.check("1.2.3.4")


def test_request_over_the_limit_is_rejected_with_429():
    limiter = RateLimiter(requests=2, window_s=60)
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")

    with pytest.raises(HTTPException) as error:
        limiter.check("1.2.3.4")

    assert error.value.status_code == 429
    assert error.value.headers is not None
    assert "Retry-After" in error.value.headers


def test_clients_are_counted_separately():
    limiter = RateLimiter(requests=1, window_s=60)
    limiter.check("1.1.1.1")

    limiter.check("2.2.2.2")  # a different client is unaffected

    with pytest.raises(HTTPException):
        limiter.check("1.1.1.1")


def test_window_frees_up_over_time(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: clock["now"])

    limiter = RateLimiter(requests=1, window_s=10)
    limiter.check("1.2.3.4")

    clock["now"] += 11
    limiter.check("1.2.3.4")  # the old hit has expired
