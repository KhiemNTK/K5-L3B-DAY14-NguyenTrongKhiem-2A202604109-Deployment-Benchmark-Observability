"""
Production AI Agent — Part 6 Final Project (bản khung)

Hoàn thành các TODO để đạt đủ 12 tiêu chí trong README.md, rồi kiểm tra:
    python check_production_ready.py

Bản khung này chạy được (uvicorn app.main:app) nhưng chưa đạt tiêu chí nào.
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask

# TODO (tiêu chí 10 — Structured logging):
#   Mỗi dòng log của app phải là 1 JSON object hợp lệ, vd
#   {"ts": "...", "lvl": "INFO", "event": "request", "path": "/ask", "status": 200, "ms": 12.3}
#   Gợi ý: tự viết logging.Formatter dùng json.dumps.
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts": self.formatTime(record, self.datefmt),
            "lvl": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "props"):
            log_obj.update(record.props)
        return json.dumps(log_obj, ensure_ascii=False)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)
logger = logging.getLogger("app")


# TODO (tiêu chí 11 — Graceful shutdown):
#   Khi nhận SIGTERM: ngừng nhận request mới, xử lý xong request đang chạy rồi thoát (exit code 0).
#   Gợi ý: dùng lifespan của FastAPI để dọn dẹp. Nếu tự đăng ký signal handler cho SIGTERM thì
#   phải gọi lại handler cũ của uvicorn, nếu không process sẽ không bao giờ tắt.
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...", extra={"props": {"event": "startup"}})
    yield
    logger.info("Application shutting down gracefully...", extra={"props": {"event": "shutdown"}})


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default=None)


# TODO (tiêu chí 4): GET /health — liveness: luôn trả 200 khi process còn chạy
#                    (kể cả khi Redis chưa kết nối được)
@app.get("/health")
def health():
    return {"status": "ok"}


# TODO (tiêu chí 5): GET /ready  — readiness: 200 khi sẵn sàng, 503 khi Redis không kết nối được
@app.get("/ready")
def ready(response: Response):
    if not redis_healthy():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unready", "reason": "redis unreachable"}
    return {"status": "ready"}


@app.post("/ask")
def ask(
    body: AskRequest,
    # TODO (tiêu chí 6): bắt buộc header X-API-Key → thêm Depends(verify_api_key)
    api_key: str = Depends(verify_api_key),
):
    start_ts = time.time()

    # TODO (tiêu chí 7): check_rate_limit(...) → 429 khi vượt giới hạn
    check_rate_limit(api_key)

    # TODO (tiêu chí 8): check_budget() trước khi gọi LLM, record_cost(...) sau khi gọi → 402 khi hết budget
    check_budget()

    answer = llm_ask(body.question)

    in_tok = max(1, len(body.question) // 4)
    out_tok = max(1, len(answer) // 4)
    cost = record_cost(in_tok, out_tok)

    duration_ms = round((time.time() - start_ts) * 1000, 2)
    logger.info(
        "Request processed",
        extra={
            "props": {
                "event": "request",
                "path": "/ask",
                "status": 200,
                "ms": duration_ms,
                "cost_usd": cost,
            }
        },
    )

    return {"question": body.question, "answer": answer}
