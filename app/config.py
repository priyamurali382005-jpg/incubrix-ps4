
import os

APP_ENV = os.environ.get("APP_ENV", "dev")

SIMULATION_MODE = (
    os.environ.get("SIMULATION_MODE", "true").lower() == "true"
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./incubrix.db"
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", "10"))

DISABLED_CONNECTORS = {
    c.strip()
    for c in os.environ.get("DISABLED_CONNECTORS", "").split(",")
    if c.strip()
}
JOBS_SYNC = os.environ.get("JOBS_SYNC", "false").lower() == "true"
JOB_WORKERS = int(os.environ.get("JOB_WORKERS", "4"))
MAX_PUBLISH_ATTEMPTS = int(os.environ.get("MAX_PUBLISH_ATTEMPTS", "3"))
BACKOFF_MAX_S = float(os.environ.get("BACKOFF_MAX_S", "60"))
CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_THRESHOLD", "5"))
CALLBACK_SECRET = os.environ.get("CALLBACK_SECRET", "change-me")