"""Week 2 execution check; this endpoint does not test the RAG pipeline."""

import json
import logging
import time
import uuid

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("erica.api")
app = FastAPI(title="ERICA Major RAG Chatbot", docs_url=None, redoc_url=None, openapi_url=None)


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
            "route": "/health" if request.url.path == "/health" else "other",
            "method": request.method,
            "status_code": status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": status_code >= 500,
        }))


@app.get("/health")
def health():
    return {"status": "ok", "service": "erica-major-rag-chatbot"}
