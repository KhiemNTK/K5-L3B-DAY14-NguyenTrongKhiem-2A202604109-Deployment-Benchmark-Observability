"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Yêu cầu:
  • Đọc REDIS_URL từ config
  • App vẫn phải KHỞI ĐỘNG ĐƯỢC khi Redis chưa sẵn sàng (đừng ping Redis lúc import)
  • redis_healthy() dùng cho GET /ready: Redis không kết nối được → False
"""
import redis
from app.config import settings

# Khởi tạo client lazy, không ping lúc import để app không crash khi thiếu Redis
try:
    r = redis.from_url(
        settings.redis_url or "redis://localhost:6379/0",
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
except Exception:
    r = None


def redis_healthy() -> bool:
    # ping Redis; lỗi kết nối → False
    try:
        if not settings.redis_url:
            return False
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
        return bool(client.ping())
    except Exception:
        return False
