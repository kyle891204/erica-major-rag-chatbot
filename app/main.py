"""ERICA handbook web interface and API."""

from collections import deque
import json
import logging
from pathlib import Path
import subprocess
from threading import BoundedSemaphore, Lock
import time
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints
from typing import Annotated

from app.rag import Answer, RagUnavailable, ask, mode

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("erica.api")
STATIC_DIR = Path(__file__).with_name("static")
ROUTES = {"/", "/health", "/api/ask", "/api/config"}
rag_slots = BoundedSemaphore(2)
recent_requests = deque()
budget_lock = Lock()
app = FastAPI(title="ERICA Major RAG Chatbot", docs_url=None, redoc_url=None, openapi_url=None)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class Question(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]


@app.middleware("http")
async def log_request(request: Request, call_next):
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        # Do not record client IPs, headers, queries, bodies or exception messages.
        logger.info(json.dumps({
            "event": "http_request",
            "request_id": request_id,
            "route": request.url.path if request.url.path in ROUTES else "other",
            "method": request.method,
            "status_code": status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": status_code >= 500,
        }))


@app.get("/health")
def health():
    return {"status": "ok", "service": "erica-major-rag-chatbot"}


@app.get("/", response_class=FileResponse)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def config():
    return {"mode": mode()}


def allow_aws_request():
    with budget_lock:
        now = time.monotonic()
        while recent_requests and now - recent_requests[0] >= 60:
            recent_requests.popleft()
        if len(recent_requests) >= 12:
            return False
        recent_requests.append(now)
        return True


@app.post("/api/ask", response_model=Answer)
def answer(body: Question):
    if not rag_slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="요청이 몰렸어요. 잠시 후 다시 시도해 주세요.")
    try:
        if mode() == "aws" and not allow_aws_request():
            raise HTTPException(status_code=429, detail="질문 요청이 많아요. 잠시 후 다시 시도해 주세요.")
        return ask(body.question)
    except (BotoCoreError, ClientError, RagUnavailable, OSError, subprocess.TimeoutExpired) as error:
        event = {"event": "rag_unavailable", "kind": type(error).__name__}
        if isinstance(error, ClientError):
            event.update(operation=error.operation_name, code=error.response["Error"]["Code"])
        logger.warning(json.dumps(event))
        raise HTTPException(status_code=503, detail="답변 서비스에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.") from None
    finally:
        rag_slots.release()
