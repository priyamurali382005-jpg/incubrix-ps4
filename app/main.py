
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request

from app import config
from app.api import router
from app.connector_api import router as connector_router
from app.mock_platforms import mock_app
from app.db import init_db
from app.errors import AppError, app_error_handler


# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(message)s",
)

log = logging.getLogger("incubrix")


# Create the FastAPI application
app = FastAPI(
    title="IncuBrix Distribution",
    version="0.1.0",
)

# Initialize the database and register API routes
init_db()
app.include_router(router, prefix="/api/v1")

# Register the custom error handler
app.add_exception_handler(
    AppError,
    app_error_handler,
)



# Log requests and return a correlation ID
@app.middleware("http")
async def correlation_and_logging(request: Request, call_next):
    cid = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    correlation_id.set(cid)
    start = time.time()
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = cid
    log_event(
        "INFO",
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        ms=round((time.time() - start) * 1000),
    )
    return response



# Health check
@app.get("/health")
def health():
    return {"status": "ok"}


# Readiness check
@app.get("/ready")
def ready():
    return {
        "status": "ready",
        "simulation_mode": config.SIMULATION_MODE,
    }


# Phase 3: Connector API
app.include_router(connector_router)

# Expose fake platforms only in simulation mode
if config.SIMULATION_MODE:
    app.mount("/mock", mock_app)
from app.logging_utils import correlation_id, log_event