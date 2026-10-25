
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
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
EVIDENCE_DIR = os.environ.get("EVIDENCE_DIR", "./evidence")
CERT_ALLOWED_HOSTS = {h.strip() for h in os.environ.get("CERT_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()}
CERT_HTTP_CHECK = os.environ.get("CERT_HTTP_CHECK", "false").lower() == "true"