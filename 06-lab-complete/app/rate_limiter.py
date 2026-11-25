"""
Rate limiting (tiêu chí 7) — sliding window lưu state trong Redis.
"""
import logging
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)
WINDOW_SECONDS = 60
_mem_requests: dict[str, list[float]] = {}


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60 giây cho mỗi API key."""
    now = time.time()
    window_start = now - WINDOW_SECONDS

    if r is None:
        timestamps = [t for t in _mem_requests.get(key, []) if t > window_start]
        if len(timestamps) >= settings.rate_limit_per_minute:
            retry_after = max(1, int(WINDOW_SECONDS - (now - timestamps[0])))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        timestamps.append(now)
        _mem_requests[key] = timestamps
        return

    redis_key = f"ratelimit:{key}"
    now = time.time()
    window_start = now - WINDOW_SECONDS

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= settings.rate_limit_per_minute:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = WINDOW_SECONDS
            if oldest:
                retry_after = max(1, int(WINDOW_SECONDS - (now - oldest[0][1])))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex[:8]}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS)
        pipe.execute()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Rate limiter Redis error: %s", type(exc).__name__)
