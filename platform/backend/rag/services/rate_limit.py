import time

from fastapi import HTTPException

from rag.core.config import RAG_REDIS_URL

_redis_client = None


def _get_client():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.Redis.from_url(RAG_REDIS_URL, decode_responses=True)
    return _redis_client


def check_rate_limit(subject: str, limit: int = 60, window_sec: int = 60) -> None:
    try:
        client = _get_client()
        bucket = int(time.time() // window_sec)
        key = f"ratelimit:{subject}:{bucket}"
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_sec)
        if count > limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        # Don't block traffic if Redis is down
        return
