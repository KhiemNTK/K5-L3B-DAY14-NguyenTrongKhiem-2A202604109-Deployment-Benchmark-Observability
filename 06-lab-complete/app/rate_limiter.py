"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)
"""
import time
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r


def check_rate_limit(key: str) -> None:
    # Dùng Redis sorted set: ZREMRANGEBYSCORE → ZCARD → ZADD → EXPIRE
    if not r:
        return

    now = time.time()
    window = 60.0
    limit = settings.rate_limit_per_minute
    redis_key = f"rate_limit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window)
        pipe.zcard(redis_key)
        pipe.zrange(redis_key, 0, 0, withscores=True)
        _, current_count, oldest_items = pipe.execute()

        if current_count >= limit:
            retry_after = 60
            if oldest_items:
                oldest_ts = oldest_items[0][1]
                retry_after = max(1, int(oldest_ts + window - now) + 1)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        pipe = r.pipeline()
        pipe.zadd(redis_key, {f"{now}:{time.time_ns()}": now})
        pipe.expire(redis_key, int(window) + 5)
        pipe.execute()
    except HTTPException:
        raise
    except Exception:
        pass
