
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.db import get_conn
from app.errors import make_error


def _now():
    return datetime.now(timezone.utc).isoformat()


def request_hash(request: dict) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


def _resolve_existing(row, h):
    if row["request_hash"] != h:
        raise make_error(
            "IDEMPOTENCY_KEY_REUSED",
            "This Idempotency-Key was already used with a different request.",
        )
    return row["job_id"], False


def submit(key: str, request: dict, cid: str | None):
    """Returns (job_id, created). created=False means: same key + same request, so reuse the job."""
    h = request_hash(request)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT request_hash, job_id FROM idempotency WHERE key = ?",
            (key,),
        ).fetchone()
        if row:
            return _resolve_existing(row, h)

        job_id = uuid.uuid4().hex
        try:
            conn.execute(
                "INSERT INTO idempotency (key, request_hash, job_id) VALUES (?,?,?)",
                (key, h, job_id),
            )
            conn.execute(
                "INSERT INTO jobs (id, status, progress, request, correlation_id, created_at, updated_at) "
                "VALUES (?, 'queued', 0, ?, ?, ?, ?)",
                (job_id, json.dumps(request), cid, _now(), _now()),
            )
            conn.commit()
            return job_id, True
        except sqlite3.IntegrityError:
            conn.rollback()
            row = conn.execute(
                "SELECT request_hash, job_id FROM idempotency WHERE key = ?",
                (key,),
            ).fetchone()
            return _resolve_existing(row, h)
    finally:
        conn.close()


def update_job(job_id: str, **fields):
    sets, values = [], []
    for name, value in fields.items():
        if name in ("result", "error"):
            value = json.dumps(value)
        sets.append(f"{name} = ?")
        values.append(value)

    sets.append("updated_at = ?")
    values.append(_now())

    conn = get_conn()
    conn.execute(
        f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?",
        (*values, job_id),
    )
    conn.commit()
    conn.close()


def get_job(job_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    job = dict(row)
    job["request"] = json.loads(job["request"])
    job["result"] = json.loads(job["result"]) if job["result"] else None
    job["error"] = json.loads(job["error"]) if job["error"] else None
    return job


def public_view(job: dict) -> dict:
    return {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "result": job["result"],
        "error": job["error"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }
