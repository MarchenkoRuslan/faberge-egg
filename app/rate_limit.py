"""
In-memory sliding-window rate limiter for protecting email-sending endpoints.

Limits are per key (e.g. client IP). Suitable for single-instance deployment;
with multiple workers/replicas each has its own counter (limit is per process).
"""
import time
from collections import defaultdict
from fastapi import Request

from app.config import settings


def _sliding_window_check(
    store: dict[str, list[float]],
    key: str,
    max_requests: int,
    window_seconds: float,
    now: float,
) -> tuple[bool, int]:
    """
    Return (allowed, retry_after_seconds). If not allowed, retry_after_seconds
    is the seconds until the oldest request in the window expires.
    """
    if key not in store:
        store[key] = []
    timestamps = store[key]
    cutoff = now - window_seconds
    timestamps[:] = [t for t in timestamps if t > cutoff]
    if len(timestamps) >= max_requests:
        oldest = min(timestamps) if timestamps else now
        retry_after = max(1, int(oldest + window_seconds - now))
        return False, retry_after
    timestamps.append(now)
    return True, 0


# In-memory store: bucket -> key -> list of request timestamps
_store: dict[str, dict[str, list[float]]] = defaultdict(dict)


def _get_client_ip_for_rate_limit(request: Request) -> str:
    """Prefer X-Forwarded-For (first client) when behind proxy (e.g. Railway)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(
    bucket: str,
    key: str,
    max_requests: int,
    window_seconds: int | float,
) -> tuple[bool, int]:
    """
    Check and consume one request from the sliding window.
    Returns (allowed, retry_after_seconds). retry_after_seconds is 0 if allowed.
    """
    now = time.monotonic()
    # Use a stable dict for this bucket
    if bucket not in _store:
        _store[bucket] = {}
    allowed, retry_after = _sliding_window_check(
        _store[bucket], key, max_requests, float(window_seconds), now
    )
    return allowed, retry_after


def require_email_rate_limit(request: Request) -> None:
    """
    Dependency: raise 429 if the client (by IP) exceeded email-sending rate limit.
    Call this on register, verify-email/request, password/forgot.
    """
    from fastapi import HTTPException, status

    key = f"ip:{_get_client_ip_for_rate_limit(request)}"
    max_req = settings.RATE_LIMIT_EMAIL_REQUESTS
    window = settings.RATE_LIMIT_EMAIL_WINDOW_SECONDS
    allowed, retry_after = check_rate_limit("email", key, max_req, window)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
