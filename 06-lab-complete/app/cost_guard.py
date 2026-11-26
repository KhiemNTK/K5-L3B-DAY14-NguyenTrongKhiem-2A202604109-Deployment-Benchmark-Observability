"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402
"""
import time
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if not r:
        return
    today = time.strftime("%Y-%m-%d")
    cost_key = f"cost:{settings.agent_api_key}:{today}"
    try:
        current_cost = float(r.get(cost_key) or 0.0)
        if current_cost >= settings.daily_budget_usd:
            raise HTTPException(
                status_code=402,
                detail=f"Budget exceeded. Current spent: ${current_cost:.6f}, limit: ${settings.daily_budget_usd:.6f}",
            )
    except HTTPException:
        raise
    except Exception:
        pass


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K
    if not r:
        return cost
    today = time.strftime("%Y-%m-%d")
    cost_key = f"cost:{settings.agent_api_key}:{today}"
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(cost_key, cost)
        pipe.expire(cost_key, 86400 * 2)
        pipe.execute()
    except Exception:
        pass
    return cost
