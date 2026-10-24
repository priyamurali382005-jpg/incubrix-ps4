
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