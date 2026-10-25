import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from app import catalogue, certification, config
from app.connections import get_connection
from app.connectors import get_connector
from app.connectors.webhook import sign
from app.errors import AppError, make_error
from app.jobs import get_job, public_view, update_job
from app.logging_utils import correlation_id, log_event
from app.rules import evaluate

_executor = ThreadPoolExecutor(max_workers=config.JOB_WORKERS)
_failures: dict[str, int] = {}   # connector key -> consecutive failures (circuit breaker)
_sim_client = None


def _sleep(seconds: float):       # separate function so tests can replace it
    time.sleep(seconds)


def reset_state():
    _failures.clear()


def _client():
    """Simulation mode talks to the in-process mock platforms. Real mode uses a normal HTTP client."""
    global _sim_client
    if not config.SIMULATION_MODE:
        return None
    if _sim_client is None:
        from fastapi.testclient import TestClient
        from app.mock_platforms import mock_app
        _sim_client = TestClient(mock_app)
    return _sim_client


def dispatch(job_id: str):
    if config.JOBS_SYNC:
        run_publication(job_id)
    else:
        _executor.submit(run_publication, job_id)


def _retry_after_seconds(err: AppError) -> float:
    try:
        wait = float(err.details.get("retry_after_s"))
    except (TypeError, ValueError):
        wait = 5.0
    return min(wait, config.BACKOFF_MAX_S)


def _publish_with_retries(connector, rendition, dest, conn, idem_key, job_id):
    last = None
    for attempt in range(1, config.MAX_PUBLISH_ATTEMPTS + 1):
        if _failures.get(connector.key, 0) >= config.CIRCUIT_BREAKER_THRESHOLD:
            raise make_error("PLATFORM_UNAVAILABLE",
                             f"{config.CIRCUIT_BREAKER_THRESHOLD} consecutive failures; not calling the platform.")
        try:
            result = connector.publish(rendition, dest, conn, idem_key)
            _failures[connector.key] = 0
            return result, attempt
        except AppError as err:
            last = err
            log_event("WARNING", "publish attempt failed", job_id=job_id,
                      attempt=attempt, code=err.code, connector=connector.key)
            if err.code == "PLATFORM_RATE_LIMIT":
                # 429 means nothing was created, so waiting for the reset time is always safe
                _sleep(_retry_after_seconds(err))
                continue
            if err.code == "PLATFORM_UNAVAILABLE":
                _failures[connector.key] = _failures.get(connector.key, 0) + 1
                if not connector.manifest.get("idempotent_publish"):
                    # We cannot tell whether the post was created. Retrying could duplicate it.
                    err.details["outcome_unknown"] = True
                    raise
                _sleep(min(2 ** attempt, config.BACKOFF_MAX_S))
                continue
            raise
    raise last


def _execute(job_id: str, req: dict) -> dict:
    dest = catalogue.get_destination(req["destination_id"])
    if not dest or not dest.get("enabled"):
        raise make_error("DESTINATION_NOT_FOUND", "Destination missing or disabled.")
    post = req["post"]

    # 1. Rules, before anything is sent
    update_job(job_id, progress=15)
    decision = evaluate(dest, post, catalogue.recent_post_times(dest["id"]))
    if not decision.allowed:
        first = decision.violations[0]
        err = make_error(first.code, first.reason, {
            "violations": [v.__dict__ for v in decision.violations],
            "retry_after": decision.retry_after})
        err.outcome = "rescheduled" if decision.action == "reschedule" else "blocked"
        raise err

    # 2. Never automate where the destination forbids it
    connector = get_connector(dest["connector_key"], client=_client())
    if not dest.get("automation_allowed") and connector.key != "assisted":
        raise make_error("DEST_AUTOMATION_NOT_ALLOWED",
                         "Automated posting is not allowed here. Use the assisted connector.")

    # 3. Format limits
    update_job(job_id, progress=35)
    check = connector.validate(post, dest, {})
    if not check["ok"]:
        raise make_error("DEST_SPEC_VIOLATION", "Content breaks the destination's limits.",
                         {"violations": check["violations"]})

    # 4. Publish (or build the pack for a person)
    update_job(job_id, progress=55)
    conn = get_connection(dest)
    result = {}
    if connector.key == "assisted":
        result["pack"] = connector.build_assist_pack(post, dest)
    outcome, attempts = _publish_with_retries(connector, post, dest, conn, job_id, job_id)
    published = outcome["status"] == "published"

    # 5. Remember it, so the weekly cap works next time
    update_job(job_id, progress=90)
    catalogue.record_post(dest["id"], "published" if published else "pending")
    result.update({"outcome": outcome["status"], "platform_post_id": outcome["platform_post_id"],
                   "live_url": outcome["live_url"], "attempts": attempts})
    return result


def run_publication(job_id: str):
    job = get_job(job_id)
    correlation_id.set(job["correlation_id"])
    update_job(job_id, status="running", progress=5)
    log_event("INFO", "job started", job_id=job_id)
    try:
        if job["request"].get("kind") == "certification":
            result = certification.certify(
                job["request"]["destination_id"]
            )
        else:
            result = _execute(job_id, job["request"])

        update_job(
            job_id,
            status="succeeded",
            progress=100,
            result=result,
        )
        log_event("INFO", "job succeeded", job_id=job_id)
    except AppError as err:
        outcome = getattr(err, "outcome", None) or (
            "unknown_outcome" if err.details.get("outcome_unknown") else "failed")
        update_job(job_id, status="failed", progress=100, result={"outcome": outcome},
                   error={"code": err.code, "message": err.message,
                          "retryable": err.retryable, "details": err.details})
        log_event("WARNING", "job failed", job_id=job_id, code=err.code, outcome=outcome)
    except Exception as exc:  # never leak internals or secrets to the caller
        log_event("ERROR", "unexpected error", job_id=job_id, error_type=type(exc).__name__)
        update_job(job_id, status="failed", progress=100, result={"outcome": "failed"},
                   error={"code": "INTERNAL_ERROR", "message": "Unexpected error.",
                          "retryable": False, "details": {}})
    _send_callback(get_job(job_id))


def _send_callback(job: dict):
    url = job["request"].get("callback_url")
    if not url:
        return
    body = json.dumps(public_view(job), sort_keys=True, separators=(",", ":")).encode()
    try:
        httpx.post(url, content=body, timeout=5, headers={
            "Content-Type": "application/json",
            "X-IncuBrix-Signature": sign(config.CALLBACK_SECRET, body)})
    except httpx.HTTPError as exc:
        log_event("WARNING", "callback failed", job_id=job["id"], error_type=type(exc).__name__)