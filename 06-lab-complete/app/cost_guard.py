"""
Cost guard (tiêu chí 8) — cộng dồn chi phí LLM vào Redis và chặn khi vượt budget.
"""
import logging
import time

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
_mem_costs: dict[str, float] = {}


def _keys() -> tuple[str, str]:
    day = time.strftime("%Y-%m-%d")
    month = time.strftime("%Y-%m")
    return f"cost:daily:{day}", f"cost:monthly:{month}"


def check_budget() -> None:
    """Gọi trước khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    daily_key, monthly_key = _keys()
    if r is None:
        daily_cost = _mem_costs.get(daily_key, 0.0)
        monthly_cost = _mem_costs.get(monthly_key, 0.0)
    else:
        try:
            daily_raw = r.get(daily_key)
            monthly_raw = r.get(monthly_key)
            daily_cost = float(daily_raw) if daily_raw else 0.0
            monthly_cost = float(monthly_raw) if monthly_raw else 0.0
        except Exception as exc:
            logger.warning("Cost guard Redis read error: %s", type(exc).__name__)
            return

    if daily_cost >= settings.daily_budget_usd or monthly_cost >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="LLM budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi sau khi gọi LLM. Cộng chi phí của request vào tổng trong Redis."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    daily_key, monthly_key = _keys()
    if r is None:
        _mem_costs[daily_key] = _mem_costs.get(daily_key, 0.0) + cost
        _mem_costs[monthly_key] = _mem_costs.get(monthly_key, 0.0) + cost
    else:
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(daily_key, cost)
            pipe.expire(daily_key, 86400 * 2)
            pipe.incrbyfloat(monthly_key, cost)
            pipe.expire(monthly_key, 86400 * 35)
            pipe.execute()
        except Exception as exc:
            logger.warning("Cost guard Redis write error: %s", type(exc).__name__)
    return round(cost, 8)
