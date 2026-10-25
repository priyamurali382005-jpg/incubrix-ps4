import time

from app import config
from app.connectors.base import load_manifest


def build(req: dict, result: dict, error: dict | None, started: float, dest: dict | None) -> dict:
    kind = req.get("kind", "publication")
    key = dest["connector_key"] if dest else None
    try:
        version = load_manifest(key)["version"] if key else None
    except OSError:
        version = None
    warnings = []
    if result.get("attempts", 1) > 1:
        warnings.append(f"Publish needed {result['attempts']} attempts.")
    if error:
        warnings.append(f"{error['code']}: {error['message']}")
    if result.get("outcome") == "unknown_outcome":
        warnings.append("Outcome unknown: the post may exist. Check the platform before retrying.")
    if result.get("result") == "failed":
        warnings.append("Certification failed; the destination was demoted.")
    if key == "devto":
        warnings.append("Dev.to has no delete call; 'delete' unpublishes the article.")
    post = req.get("post") or {}
    return {
        "manifest_version": "1.0",
        "kind": kind,
        "providers": [{"type": "connector", "key": key, "version": version}],
        "models": [],                      # no AI model is used in this service
        "ai_used": False,
        "settings": {"simulation_mode": config.SIMULATION_MODE,
                     "max_publish_attempts": config.MAX_PUBLISH_ATTEMPTS,
                     "backoff_max_s": config.BACKOFF_MAX_S,
                     "circuit_breaker_threshold": config.CIRCUIT_BREAKER_THRESHOLD,
                     "http_timeout_s": config.HTTP_TIMEOUT_S},
        "seed": None,                      # nothing here is random
        "timings": {"total_s": round(time.monotonic() - started, 3)},
        "cost_estimate": {"currency": "USD", "amount": 0.0,
                          "note": "No paid API or model is called."},
        "warnings": warnings,
        "rights": {"content_ai_generated": bool(post.get("ai_generated")),
                   "ai_disclosure_included": bool(post.get("ai_disclosure_included")),
                   "software_licences": "see SOURCES.md",
                   "default_path_commercial_use": True},
    }
