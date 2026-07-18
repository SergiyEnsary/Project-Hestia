from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class ConfigurableRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, request: Request) -> None:
        limit = request.app.state.config.security.rate_limit_per_minute
        host = request.client.host if request.client else "unknown"
        route = request.url.path
        key = f"{host}:{route}"
        now = time.monotonic()
        cutoff = now - 60.0
        async with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"},
                )
            timestamps.append(now)
            if len(self._requests) > 10_000:
                self._requests = defaultdict(
                    deque,
                    {
                        item_key: values
                        for item_key, values in self._requests.items()
                        if values and values[-1] > cutoff
                    },
                )
