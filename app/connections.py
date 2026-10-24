
import json
import os

from app import config
from app.errors import make_error


def _sim():
    return {
        "discourse": {
            "base_url": "http://mock/discourse",
            "api_key": "sim-key",
            "username": "sim",
        },
        "devto": {
            "base_url": "http://mock/devto",
            "api_key": "sim-key",
        },
        "webhook": {
            "base_url": "http://mock/webhook/receive",
            "secret": os.environ.get("MOCK_WEBHOOK_SECRET", "demo-secret"),
        },
        "assisted": {},
    }


def get_connection(destination: dict) -> dict:
    key = destination["connector_key"]
    if config.SIMULATION_MODE:
        return _sim().get(key, {})
    raw = os.environ.get(f"CONN_{destination['id']}")
    if not raw:
        if key == "assisted":
            return {}
        raise make_error(
            "CONNECTION_MISSING",
            f"No credentials configured for destination {destination['id']}.",
        )
    return json.loads(raw)
