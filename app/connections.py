import json
import os
from pathlib import Path

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


def _from_file(destination: dict) -> dict:
    filename = config.CONN_FILE
    if not filename:
        return {}

    path = Path(filename)
    if not path.is_file():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise make_error(
            "CONNECTION_MISSING",
            "Connection configuration file must contain valid JSON.",
        )

    return data.get(destination["id"]) or data.get(destination["connector_key"]) or {}


def get_connection(destination: dict) -> dict:
    key = destination["connector_key"]

    if config.SIMULATION_MODE:
        return _sim().get(key, {})

    raw = (
        os.environ.get(f"CONN_{destination['id']}")
        or os.environ.get(f"CONN_{key.upper()}")
    )

    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise make_error(
                "CONNECTION_MISSING",
                f"Credentials for destination {destination['id']} must be valid JSON.",
            )

    file_connection = _from_file(destination)
    if file_connection:
        return file_connection

    if key == "assisted":
        return {}

    raise make_error(
        "CONNECTION_MISSING",
        f"No credentials configured for destination {destination['id']}.",
    )