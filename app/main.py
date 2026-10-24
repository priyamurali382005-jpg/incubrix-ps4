
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request

from app import config
from app.api import router
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
async def correlation_and_logging(
    request: Request,
    call_next,
):
    correlation_id = request.headers.get(
        "X-Correlation-Id",
        str(uuid.uuid4()),
    )

    start = time.time()

    response = await call_next(request)

    response.headers["X-Correlation-Id"] = correlation_id

    log.info(
        json.dumps({
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "level": "INFO",
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round(
                (time.time() - start) * 1000
            ),
        })
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
