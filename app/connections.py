
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
        "lemmy": {
            "base_url": "http://mock/lemmy",
            "username": "sim",
            "password": "sim-pass",
        },
        "ghost": {
            "base_url": "http://mock/ghost",
            "admin_key": "simid:" + "00" * 32,
        },
    }


def get_connection(destination: dict) -> dict:
    key = destination["connector_key"]

    if config.SIMULATION_MODE:
        return _sim().get(key, {})

    raw = (
        os.environ.get(f"CONN_{destination['id']}")
        or os.environ.get(f"CONN_{key.upper()}")
    )

    if not raw:
        if key == "assisted":
            return {}

        raise make_error(
            "CONNECTION_MISSING",
            f"No credentials configured for destination {destination['id']}.",
        )

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise make_error(
            "CONNECTION_MISSING",
            f"Credentials for destination {destination['id']} must be valid JSON.",
        )
