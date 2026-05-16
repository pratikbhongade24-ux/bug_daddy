import time
import redis
from fastapi import HTTPException

from app.core.config import settings

client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def check_rate_limit(subject: str, limit: int = 60, window_sec: int = 60):
    try:
        bucket = int(time.time() // window_sec)
        key = f'ratelimit:{subject}:{bucket}'
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_sec)
        if count > limit:
            raise HTTPException(status_code=429, detail='Rate limit exceeded')
    except redis.RedisError:
        # Do not fail user traffic if Redis is temporarily unavailable.
        return
