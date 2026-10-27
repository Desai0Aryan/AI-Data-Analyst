"""Abuse and cost protection.

Two independent guards for the LLM-backed endpoints (a public demo can otherwise burn your API budget):
  * a per-client sliding-window rate limit
  * a global daily budget of LLM-backed requests (skipped for the free replay provider)
A limit of 0 disables the guard. State is in memory: right for one process; use Redis if you scale out.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from .config import get_settings


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float = 60.0) -> int:
        """Record a request. Returns 0 if allowed, else the seconds until the client may retry."""
        if limit <= 0:
            return 0
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(q[0] + window_s - now) + 1)
            q.append(now)
            return 0

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


class DailyBudget:
    def __init__(self) -> None:
        self._day = ""
        self._used = 0
        self._lock = threading.Lock()

    def take(self, limit: int) -> bool:
        if limit <= 0:
            return True
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            if today != self._day:
                self._day, self._used = today, 0
            if self._used >= limit:
                return False
            self._used += 1
            return True

    def clear(self) -> None:
        with self._lock:
            self._day, self._used = "", 0


windows = SlidingWindow()
budget = DailyBudget()


def reset() -> None:
    windows.clear()
    budget.clear()


def client_id(request: Request) -> str:
    """The caller's address. X-Forwarded-For is trusted only when TRUST_PROXY is set (otherwise
    anyone could dodge the limit by sending their own header)."""
    if get_settings().trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many(code: str, message: str, retry_after: int) -> HTTPException:
    return HTTPException(status_code=429, headers={"Retry-After": str(retry_after)},
                         detail={"stage": "limits", "code": code, "message": message})


def guard_llm(request: Request) -> None:
    """Dependency for endpoints that can cost money."""
    s = get_settings()
    wait = windows.hit(f"ask:{client_id(request)}", s.rate_limit_per_minute)
    if wait:
        raise _too_many("rate_limited", f"Too many questions. Try again in {wait} seconds.", wait)
    if s.llm_provider.lower() != "replay" and not budget.take(s.daily_llm_budget):
        raise _too_many("budget_exhausted", "The daily question budget for this demo is used up. It resets at midnight UTC.", 3600)


def guard_cheap(bucket: str, per_minute: int):
    """Dependency factory for DB-only endpoints that are still worth protecting."""
    def dep(request: Request) -> None:
        wait = windows.hit(f"{bucket}:{client_id(request)}", per_minute)
        if wait:
            raise _too_many("rate_limited", f"Too many requests. Try again in {wait} seconds.", wait)
    return dep
