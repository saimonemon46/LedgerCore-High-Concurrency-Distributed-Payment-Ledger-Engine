"""Redis-backed sliding/fixed-window rate limiter with in-memory fallback.

Enforces HTTP 429 Too Many Requests on high-throughput endpoints such as
`POST /api/v1/transfers`. Uses Redis atomic pipelines in production and
falls back to a thread-safe in-memory window when Redis is unreachable.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

from redis.asyncio import Redis

logger = logging.getLogger("ledger_core.rate_limiter")


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a single rate-limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class RedisRateLimiter:
    """Distributed Redis rate limiter with thread-safe local fallback."""

    def __init__(
        self,
        redis_url: str,
        requests_per_minute: int = 300,
        window_seconds: int = 60,
    ) -> None:
        self._redis_url = redis_url
        self.requests_per_minute = max(1, requests_per_minute)
        self.window_seconds = max(1, window_seconds)
        self._redis: Redis | None = None
        self._local_lock = threading.Lock()
        self._local_windows: dict[str, deque[float]] = {}

    def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
        return self._redis

    async def close(self) -> None:
        """Closes underlying Redis connection pool if initialized."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    def _check_local(self, key: str) -> RateLimitResult:
        now = time.time()
        cutoff = now - self.window_seconds
        with self._local_lock:
            window = self._local_windows.setdefault(key, deque())
            while window and window[0] < cutoff:
                window.popleft()
            current = len(window)
            if current >= self.requests_per_minute:
                oldest = window[0]
                reset_secs = max(1, int(self.window_seconds - (now - oldest)))
                return RateLimitResult(
                    allowed=False,
                    limit=self.requests_per_minute,
                    remaining=0,
                    reset_seconds=reset_secs,
                )
            window.append(now)
            remaining = max(0, self.requests_per_minute - len(window))
            return RateLimitResult(
                allowed=True,
                limit=self.requests_per_minute,
                remaining=remaining,
                reset_seconds=self.window_seconds,
            )

    async def check(self, client_key: str, scope: str = "transfers") -> RateLimitResult:
        """Checks and increments the request counter for `client_key`."""
        bucket = int(time.time() // self.window_seconds)
        redis_key = f"ledger:ratelimit:{scope}:{client_key}:{bucket}"
        try:
            client = self._get_redis()
            async with client.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, self.window_seconds)
                results = await pipe.execute()
            count = int(results[0])
            remaining = max(0, self.requests_per_minute - count)
            reset_secs = max(
                1,
                self.window_seconds - int(time.time() % self.window_seconds),
            )
            return RateLimitResult(
                allowed=count <= self.requests_per_minute,
                limit=self.requests_per_minute,
                remaining=remaining,
                reset_seconds=reset_secs,
            )
        except Exception as exc:
            logger.debug("Redis rate limiter unavailable (%s); using local fallback.", exc)
            return self._check_local(f"{scope}:{client_key}")
