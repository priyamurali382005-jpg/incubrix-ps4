
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

# --- phase6 additions ---

import os as _os
API_TOKEN = _os.environ.get("API_TOKEN", "")
RATE_LIMIT_PER_MIN = int(_os.environ.get("RATE_LIMIT_PER_MIN", "0"))
TRUST_PROXY_HEADERS = _os.environ.get("TRUST_PROXY_HEADERS", "false").lower() == "true"
MOCK_BASE_URL = _os.environ.get("MOCK_BASE_URL", "").rstrip("/")
CONN_FILE = _os.environ.get("CONN_FILE", "")
SEED_CSV = _os.environ.get("SEED_CSV", "")
PUBLIC_BASE_URL = _os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
STORAGE_BACKEND = _os.environ.get("STORAGE_BACKEND", "local")
FILES_DIR = _os.environ.get("FILES_DIR", "./files")
S3_ENDPOINT = _os.environ.get("S3_ENDPOINT", "")
S3_PUBLIC_ENDPOINT = _os.environ.get("S3_PUBLIC_ENDPOINT", "")
S3_ACCESS_KEY = _os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = _os.environ.get("S3_SECRET_KEY", "")
S3_BUCKET = _os.environ.get("S3_BUCKET", "incubrix-outputs")
S3_REGION = _os.environ.get("S3_REGION", "us-east-1")
S3_URL_EXPIRES_S = int(_os.environ.get("S3_URL_EXPIRES_S", "3600"))
MAX_UPLOAD_BYTES = int(_os.environ.get("MAX_UPLOAD_BYTES", "5000000"))
ALLOW_PRIVATE_FETCH = _os.environ.get("ALLOW_PRIVATE_FETCH", "false").lower() == "true"
