import json
import pathlib
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app import catalogue, config, storage
from app.connections import get_connection
from app.connectors import get_connector
from app.db import get_conn
from app.errors import AppError, make_error
from app.logging_utils import log_event, redact

TRANSIENT = {"PLATFORM_RATE_LIMIT", "PLATFORM_UNAVAILABLE", "PLATFORM_QUOTA_EXHAUSTED"}
LEVEL_BY_TIER = {"native": "L3", "bridge": "L2", "feed": "L2", "protocol": "L2", "assisted": "L1"}
DELETE_DEADLINE_S = 600  # the brief: test posts are deleted within 10 minutes


def _now():
    return datetime.now(timezone.utc).isoformat()


class StepFailed(Exception):
    def __init__(self, step, code, message):
        super().__init__(message)
        self.step, self.code, self.message = step, code, message


class Recorder:
    """Runs one step, times it and records the outcome. Any failure becomes StepFailed."""

    def __init__(self):
        self.steps = []

    def run(self, name, fn):
        start = time.monotonic()
        try:
            out = fn()
        except AppError as err:
            self._add(name, False, start, {"code": err.code, "message": err.message, "details": err.details})
            raise StepFailed(name, err.code, err.message)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            # The platform answered, but not in the shape the connector expects: API drift.
            msg = f"Platform response no longer matches the connector ({type(exc).__name__}: {exc})"
            self._add(name, False, start, {"code": "PLATFORM_RESPONSE_CHANGED", "message": msg})
            raise StepFailed(name, "PLATFORM_RESPONSE_CHANGED", msg)
        self._add(name, True, start, {})
        return out

    def _add(self, name, ok, start, detail):
        self.steps.append({"step": name, "ok": ok, "ms": round((time.monotonic() - start) * 1000), **detail})


def _guard(conn_info, dest, connector):
    """Test posts go only to hosts you listed. Simulation mode and assisted never touch a real host."""
    if config.SIMULATION_MODE or connector.key == "assisted":
        return
    host = urlparse(conn_info.get("base_url") or dest["url"]).hostname
    if host not in config.CERT_ALLOWED_HOSTS:
        raise make_error("CERT_TARGET_NOT_ALLOWED",
                         f"Certification posts may only go to CERT_ALLOWED_HOSTS; '{host}' is not listed.",
                         {"host": host})


def _confirm_live(connector, post_id, conn, ev):
    status = connector.get_status(post_id, conn)
    if status["status"] != "published" or not status.get("live_url"):
        raise make_error("CERT_CHECK_FAILED", "Platform does not report the post as live.", {"status": status})
    ev["status_read"] = status
    ev["http_check"] = "skipped"
    if config.CERT_HTTP_CHECK and not config.SIMULATION_MODE:
        try:
            r = httpx.get(status["live_url"], timeout=config.HTTP_TIMEOUT_S, follow_redirects=True)
        except httpx.HTTPError:
            raise make_error("CERT_CHECK_FAILED", "Live URL could not be reached.")
        if r.status_code >= 400:
            raise make_error("CERT_CHECK_FAILED", f"Live URL returned HTTP {r.status_code}.")
        ev["http_check"] = r.status_code


def _confirm_deleted(connector, post_id, conn):
    status = connector.get_status(post_id, conn)
    if status["status"] != "deleted":
        raise make_error("CERT_CHECK_FAILED", "Post is still reported as present after delete.", {"status": status})


def _cleanup(connector, post_id, conn, deleted, attempted_publish, rec):
    """Runs even when a step failed, so test posts are never left behind."""
    if deleted or not attempted_publish:
        return {"status": "not_needed"}
    if post_id is None:
        return {"status": "post_id_unknown",
                "warning": "A test post may exist on the platform. Remove it by hand."}
    try:
        connector.delete(post_id, conn)
        return {"status": "deleted"}
    except Exception as exc:  # cleanup must never raise
        return {"status": "failed", "error": type(exc).__name__,
                "warning": f"Test post {post_id} may still exist. Remove it by hand."}


def _certify_api(connector, dest, conn, rec, ev):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rendition = {"title": f"[IncuBrix certification test] {stamp}",
                 "body": "Automated certification test post. It is deleted within minutes. No action needed.",
                 "links": [], "tags": []}
    ev["test_rendition"] = rendition
    post_id, deleted, attempted, published_at = None, False, False, None

    def validate():
        out = connector.validate(rendition, dest, conn)
        if not out["ok"]:
            raise make_error("DEST_SPEC_VIOLATION", "Test post breaks the destination's limits.",
                             {"violations": out["violations"]})

    try:
        rec.run("validate", validate)
        attempted = True
        pub = rec.run("publish", lambda: connector.publish(rendition, dest, conn, f"cert-{dest['id']}-{stamp}"))
        post_id, published_at = str(pub["platform_post_id"]), time.monotonic()
        ev["platform_post_id"], ev["live_url"] = post_id, pub["live_url"]
        rec.run("confirm_live", lambda: _confirm_live(connector, post_id, conn, ev))
        rec.run("delete", lambda: connector.delete(post_id, conn))
        deleted = True
        ev["seconds_publish_to_delete"] = round(time.monotonic() - published_at, 2)
        ev["deleted_within_10_min"] = ev["seconds_publish_to_delete"] < DELETE_DEADLINE_S
        rec.run("confirm_deleted", lambda: _confirm_deleted(connector, post_id, conn))
    finally:
        ev["cleanup"] = _cleanup(connector, post_id, conn, deleted, attempted, rec)


def _certify_assisted(connector, dest, rec, ev):
    rendition = {"title": "[IncuBrix certification test]", "body": "Pack check.", "links": []}
    pack = rec.run("build_pack", lambda: connector.build_assist_pack(rendition, dest))

    def check():
        missing = [k for k in ("files", "caption", "deep_link", "checklist") if not pack.get(k)]
        if missing:
            raise make_error("CERT_CHECK_FAILED", "Assist pack is incomplete.", {"missing": missing})

    rec.run("check_pack", check)
    ev["cleanup"] = {"status": "not_needed"}


def _alert(dest_id, severity, message):
    conn = get_conn()
    conn.execute("INSERT INTO alerts (destination_id, severity, message, created_at) VALUES (?,?,?,?)",
                 (dest_id, severity, message, _now()))
    conn.commit()
    conn.close()
    log_event(severity, message, destination_id=dest_id)


def _apply_result(dest, connector, ev):
    if ev["result"] == "passed":
        level = LEVEL_BY_TIER.get(connector.manifest["tier"], "L1")
        catalogue.update_destination(dest["id"], level=level, last_certified_at=ev["finished_at"], enabled=1)
        ev["new_level"] = level
    elif ev["result"] == "failed":
        catalogue.update_destination(dest["id"], enabled=0, level="L0")
        _alert(dest["id"], "ERROR",
               f"Destination '{dest['name']}' demoted: step '{ev['failed_step']}' failed with {ev['error_code']}.")
    else:
        _alert(dest["id"], "WARNING",
               f"Certification of '{dest['name']}' was inconclusive ({ev['error_code']}). Not demoted.")
    if ev["cleanup"]["status"] in ("post_id_unknown", "failed"):
        _alert(dest["id"], "ERROR", f"Manual cleanup needed on '{dest['name']}': {ev['cleanup']['warning']}")


def _save(ev):
    out_dir = pathlib.Path(config.EVIDENCE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = out_dir / f"cert_dest{ev['destination_id']}_{stamp}.json"
    ev["evidence_path"] = str(path)
    text = redact(json.dumps(ev, indent=2, default=str))   # secrets never reach the evidence file
    path.write_text(text)
    conn = get_conn()
    conn.execute(
        "INSERT INTO certifications (destination_id, connector_key, result, failed_step, total_seconds,"
        " evidence_path, evidence, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (ev["destination_id"], ev["connector_key"], ev["result"], ev.get("failed_step"),
         ev["total_seconds"], str(path), text, _now()))
    conn.commit()
    conn.close()


def certify(destination_id: int) -> dict:
    from app.workflow import _client

    dest = catalogue.get_destination(destination_id)
    if not dest:
        raise make_error("DESTINATION_NOT_FOUND", "No such destination.")

    connector = get_connector(dest["connector_key"], client=_client())

    # Check the allowed host before requiring credentials in real mode.
    if not config.SIMULATION_MODE and connector.key != "assisted":
        _guard({}, dest, connector)

    conn = get_connection(dest)

    if config.SIMULATION_MODE or connector.key == "assisted":
        _guard(conn, dest, connector)

    started = time.monotonic()
    rec = Recorder()
    ev = {
        "destination_id": dest["id"],
        "destination_name": dest["name"],
        "connector_key": connector.key,
        "connector_version": connector.manifest["version"],
        "tier": connector.manifest["tier"],
        "simulation_mode": config.SIMULATION_MODE,
        "started_at": _now(),
    }
    failure = None

    try:
        if connector.key == "assisted":
            _certify_assisted(connector, dest, rec, ev)
        else:
            _certify_api(connector, dest, conn, rec, ev)
    except StepFailed as exc:
        failure = exc

    ev["result"] = (
        "passed"
        if failure is None
        else ("inconclusive" if failure.code in TRANSIENT else "failed")
    )
    ev["failed_step"] = failure.step if failure else None
    ev["error_code"] = failure.code if failure else None
    ev["steps"] = rec.steps
    ev["total_seconds"] = round(time.monotonic() - started, 2)
    ev["finished_at"] = _now()

    _apply_result(dest, connector, ev)
    _save(ev)
    log_event(
        "INFO",
        "certification finished",
        destination_id=dest["id"],
        result=ev["result"],
    )

    return ev
def history(destination_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, result, failed_step, total_seconds, evidence_path, created_at "
        "FROM certifications WHERE destination_id = ? ORDER BY id DESC", (destination_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]